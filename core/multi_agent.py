"""
Moruk AI OS - Multi-Agent Orchestrator v2
Spawnt parallele KI-Agenten mit spezifischen Rollen.

v2 Änderungen:
- SharedMemory direkt integriert (kein fragiler Plugin-Import mehr)
- Intelligentes Auto-Planning: Brain analysiert Task und spawnt passende Agenten
- DeepThink als Reviewer (fix: _call_llm → review_multi_agent)
- Agenten können Ergebnisse vorheriger Agenten lesen (DAG-aware)
- Neue Rollen: architect, designer (zusätzlich zu coder, writer, reviewer, researcher)
- Task-Größe bestimmt Anzahl Agenten

Rollen:
  researcher  — Recherchiert/analysiert, gibt strukturierte Infos zurück
  architect   — Entwirft Systemarchitektur, Dateistruktur, Schnittstellen
  coder       — Schreibt/editiert Code-Dateien
  designer    — UI/UX Design, CSS, Layout-Entscheidungen
  writer      — Erstellt Texte, Docs, Summaries
  reviewer    — Reviewed Output anderer Agenten (kann auch DeepThink sein)
  executor    — Führt Shell-Befehle aus
"""

PLUGIN_NAME = "multi_agent"
PLUGIN_DESCRIPTION = (
    "Spawn parallel AI agents with specific roles. "
    "Use for: complex projects, parallel code+design+review, multi-perspective analysis. "
    "Roles: researcher, architect, coder, designer, writer, reviewer, executor."
)
PLUGIN_PARAMS = (
    '"agents": [{"role": "researcher|architect|coder|designer|writer|reviewer|executor", '
    '"task": "what to do", "context": "optional extra context"}], '
    '"timeout": 120  |  OR simply: "task": "description" for auto-planning'
)
PLUGIN_CORE = False

import threading
import queue
import subprocess
import shlex
import os
import time
import json
import re
from core.logger import get_logger

log = get_logger("multi_agent")


# ══════════════════════════════════════════════════════════════
# Inline Shared Memory (thread-safe, kein Plugin-Import nötig)
# ══════════════════════════════════════════════════════════════

class AgentSharedMemory:
    """Thread-safe shared memory für Agent-Koordination während eines Runs."""

    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def store(self, key: str, value):
        with self._lock:
            self._data[key] = value

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def get_all_agent_results(self) -> dict:
        """Gibt alle Agent-Ergebnisse zurück."""
        with self._lock:
            return {k: v for k, v in self._data.items() if k.startswith("agent_")}

    def clear(self):
        with self._lock:
            self._data.clear()


# ══════════════════════════════════════════════════════════════
# Agent Rollen & Prompts
# ══════════════════════════════════════════════════════════════

# Von ToolRouter gesetzt
_brain = None

ROLE_PROMPTS = {
    "researcher": (
        "You are a Research Agent. Gather, analyze and structure information. "
        "Use web_search, read_file, file_manager. End with a clear SUMMARY section. "
        "Focus on facts and data. Cite sources where possible."
    ),
    "architect": (
        "You are a Software Architect Agent. Design the system structure, "
        "define file organization, interfaces, and data flow. "
        "Output a clear ARCHITECTURE document with: file list, responsibilities, "
        "interfaces between components, and dependency order. "
        "Do NOT write implementation code — only structure and specs."
    ),
    "coder": (
        "You are a Coding Agent. Write, edit and test code. "
        "Always use write_file to save your work. Run syntax checks after writing .py files. "
        "Follow the architecture/specs if provided by other agents. "
        "End with a summary of files created/modified."
    ),
    "designer": (
        "You are a UI/UX Designer Agent. Design user interfaces, "
        "create CSS/styling, layout structures, and visual hierarchy. "
        "Use write_file to save CSS, HTML templates, or Qt widget code. "
        "Focus on: readability, consistent spacing, color scheme, responsive layout. "
        "End with a summary of design decisions."
    ),
    "writer": (
        "You are a Writer Agent. Create clear, well-structured text content. "
        "Use write_file to save documents. End with a summary of what was created."
    ),
    "reviewer": (
        "You are a Review Agent. Critically evaluate work from other agents. "
        "Look for: bugs, logic errors, inconsistencies, missing edge cases, quality issues. "
        "Return a structured review: APPROVED/NEEDS_FIXES, Issues list, Suggestions. "
        "Be constructive — explain HOW to fix issues, not just what's wrong."
    ),
    "executor": (
        "You are an Execution Agent. Run shell commands via terminal tool. "
        "Report exact output. Handle errors gracefully."
    ),
}

# Task-Komplexität → Agenten-Vorschlag
COMPLEXITY_PROFILES = {
    "simple": {
        "description": "Single-file change, simple command, quick fix",
        "max_agents": 2,
        "typical_roles": ["coder"],
    },
    "medium": {
        "description": "Multi-file change, feature implementation",
        "max_agents": 4,
        "typical_roles": ["architect", "coder", "reviewer"],
    },
    "complex": {
        "description": "New module, UI+backend, multi-component project",
        "max_agents": 6,
        "typical_roles": ["architect", "coder", "designer", "reviewer"],
    },
    "research": {
        "description": "Analysis, research, documentation",
        "max_agents": 3,
        "typical_roles": ["researcher", "writer", "reviewer"],
    },
}


# ══════════════════════════════════════════════════════════════
# Agent Execution
# ══════════════════════════════════════════════════════════════

def _run_agent(
    agent_def: dict,
    result_queue: queue.Queue,
    idx: int,
    timeout: int,
    shared_mem: AgentSharedMemory,
):
    """Führt einen einzelnen Agenten aus."""
    role = agent_def.get("role", "executor")
    task = agent_def.get("task", "")
    context = agent_def.get("context", "")
    depends_on = agent_def.get("depends_on", [])
    start_time = time.time()

    try:
        # ── Executor: Direkte Shell-Befehle ──
        if role == "executor":
            try:
                args = shlex.split(task)
                out = subprocess.check_output(
                    args,
                    shell=False,
                    timeout=timeout,
                    stderr=subprocess.STDOUT,
                    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                )
                output = out.decode(errors="replace").strip()[:2000]
                status = "ok"
            except Exception as e:
                output = str(e)
                status = "error"

            result_queue.put((idx, {
                "role": role, "task": task, "status": status,
                "output": output, "duration": round(time.time() - start_time, 1),
            }))
            return

        # ── Brain-basierte Agenten ──
        if _brain is None:
            result_queue.put((idx, {
                "role": role, "task": task, "status": "error",
                "output": "Brain not connected to multi_agent plugin",
                "duration": 0,
            }))
            return

        role_system = ROLE_PROMPTS.get(role, ROLE_PROMPTS["executor"])

        # Shared Memory: Ergebnisse von abhängigen Agenten laden
        shared_ctx = ""
        for dep_idx in depends_on:
            dep_result = shared_mem.get(f"agent_{dep_idx}_result")
            dep_role = shared_mem.get(f"agent_{dep_idx}_role", "unknown")
            if dep_result:
                shared_ctx += (
                    f"\n\n[RESULT FROM {dep_role.upper()} AGENT (#{dep_idx})]:\n"
                    f"{str(dep_result)[:800]}"
                )

        # Auch andere bereits fertige Agenten als Kontext
        all_results = shared_mem.get_all_agent_results()
        for key, val in all_results.items():
            if key.endswith("_result"):
                prev_idx_str = key.replace("agent_", "").replace("_result", "")
                try:
                    prev_idx = int(prev_idx_str)
                    if prev_idx not in depends_on and prev_idx != idx:
                        prev_role = shared_mem.get(f"agent_{prev_idx}_role", "unknown")
                        shared_ctx += (
                            f"\n\n[FYI — {prev_role.upper()} Agent #{prev_idx}]:\n"
                            f"{str(val)[:400]}"
                        )
                except ValueError:
                    pass

        full_context = f"[AGENT ROLE: {role.upper()}]\n{role_system}"
        if context:
            full_context += f"\n\nExtra Context:\n{context}"
        if shared_ctx:
            full_context += f"\n\n{'='*40}\nSHARED MEMORY — Results from other agents:{shared_ctx}"

        response = _brain.think(
            task,
            extra_context=full_context,
            max_iterations=12,
            depth=3,
            isolated=True,
        )

        # Ergebnis in Shared Memory speichern
        shared_mem.store(f"agent_{idx}_result", (response or "")[:1500])
        shared_mem.store(f"agent_{idx}_role", role)

        result_queue.put((idx, {
            "role": role, "task": task, "status": "ok",
            "output": (response or "(no output)")[:3000],
            "duration": round(time.time() - start_time, 1),
        }))

    except Exception as e:
        result_queue.put((idx, {
            "role": role, "task": task, "status": "error",
            "output": f"Agent error: {e}",
            "duration": round(time.time() - start_time, 1),
        }))


# ══════════════════════════════════════════════════════════════
# Smart Planning
# ══════════════════════════════════════════════════════════════

def _estimate_complexity(task: str) -> str:
    """Schätzt die Komplexität eines Tasks anhand von Keywords."""
    task_lower = task.lower()

    complex_keywords = [
        "project", "system", "redesign", "refactor entire", "new module",
        "full stack", "ui und backend", "frontend and backend", "multi-file",
        "architektur", "architecture",
    ]
    medium_keywords = [
        "implement", "feature", "add", "create", "fix bug", "update",
        "modify", "change", "improve", "erweitern", "hinzufügen",
    ]
    research_keywords = [
        "research", "analyze", "compare", "evaluate", "document",
        "recherchiere", "analysiere", "vergleiche",
    ]

    if any(kw in task_lower for kw in complex_keywords):
        return "complex"
    if any(kw in task_lower for kw in research_keywords):
        return "research"
    if any(kw in task_lower for kw in medium_keywords):
        return "medium"
    return "simple"


def _plan_agents(task: str) -> list:
    """Intelligentes Auto-Planning: Brain + Heuristik entscheiden über Agenten."""
    complexity = _estimate_complexity(task)
    profile = COMPLEXITY_PROFILES[complexity]

    if _brain is None:
        # Fallback ohne Brain: Heuristik-basiert
        return _heuristic_plan(task, profile)

    try:
        available_roles = ", ".join(ROLE_PROMPTS.keys())
        plan_prompt = (
            f"Task: {task}\n\n"
            f"Estimated complexity: {complexity} ({profile['description']})\n"
            f"Max agents: {profile['max_agents']}\n"
            f"Available roles: {available_roles}\n\n"
            "Decide which agents to spawn. Return ONLY JSON:\n"
            '{"agents": [{"role": "...", "task": "specific subtask", '
            '"depends_on": [indices of agents this depends on]}]}\n\n'
            "Rules:\n"
            f"- Max {profile['max_agents']} agents\n"
            "- Each agent has a clear focused subtask\n"
            "- Use depends_on to define execution order ([] = can run immediately)\n"
            "- For code tasks: architect first, then coders, then reviewer\n"
            "- For UI tasks: include a designer agent\n"
            "- ALWAYS include a reviewer as the last agent\n"
            "- Only spawn what is really needed — don't over-engineer simple tasks"
        )
        raw = _brain.think(plan_prompt, max_iterations=2, depth=2, isolated=True)

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            agents = parsed.get("agents", [])
            if agents:
                # Validierung: depends_on darf nur auf vorherige Agenten zeigen
                for i, agent in enumerate(agents):
                    deps = agent.get("depends_on", [])
                    agent["depends_on"] = [d for d in deps if isinstance(d, int) and 0 <= d < i]

                # Max Agents respektieren
                agents = agents[:profile["max_agents"]]

                log.info(
                    f"Auto-planned {len(agents)} agents ({complexity}): "
                    f"{[a.get('role') for a in agents]}"
                )
                return agents
    except Exception as e:
        log.warning(f"Agent planning failed: {e}")

    return _heuristic_plan(task, profile)


def _heuristic_plan(task: str, profile: dict) -> list:
    """Fallback-Planning ohne Brain: Nutzt das Complexity-Profile."""
    agents = []
    task_lower = task.lower()

    roles = profile["typical_roles"]

    for i, role in enumerate(roles):
        agent = {
            "role": role,
            "task": task if role in ("coder", "researcher") else f"Review/support for: {task}",
            "depends_on": [],
        }

        # Abhängigkeiten: Reviewer hängt von allen anderen ab
        if role == "reviewer":
            agent["depends_on"] = list(range(i))
            agent["task"] = f"Review all results for: {task}"
        # Coder hängt von Architect ab
        elif role == "coder" and "architect" in roles:
            arch_idx = roles.index("architect")
            agent["depends_on"] = [arch_idx]
        # Designer hängt von Architect ab
        elif role == "designer" and "architect" in roles:
            arch_idx = roles.index("architect")
            agent["depends_on"] = [arch_idx]

        agents.append(agent)

    log.info(f"Heuristic plan: {[a['role'] for a in agents]}")
    return agents


# ══════════════════════════════════════════════════════════════
# Parallel Execution mit DAG-Awareness
# ══════════════════════════════════════════════════════════════

def _identify_execution_groups(agents: list) -> list:
    """Topological Sort: Gruppiert Agenten nach Abhängigkeiten für parallele Ausführung."""
    n = len(agents)
    groups = []
    completed = set()
    remaining = list(range(n))

    for _ in range(n):
        if not remaining:
            break

        ready = []
        still_waiting = []

        for idx in remaining:
            deps = agents[idx].get("depends_on", [])
            if all(d in completed for d in deps):
                ready.append(idx)
            else:
                still_waiting.append(idx)

        if not ready:
            log.warning(f"Circular dependency detected, running {still_waiting} sequentially")
            for i in still_waiting:
                groups.append([i])
            break

        groups.append(ready)
        for idx in ready:
            completed.add(idx)
        remaining = still_waiting

    return groups


def _execute_agent_group(
    agents: list,
    group: list,
    timeout: int,
    shared_mem: AgentSharedMemory,
) -> dict:
    """Führt eine Gruppe von Agenten parallel aus."""
    result_queue = queue.Queue()
    threads = []

    for idx in group:
        t = threading.Thread(
            target=_run_agent,
            args=(agents[idx], result_queue, idx, timeout, shared_mem),
            daemon=True,
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=timeout + 5)

    results = {}
    while not result_queue.empty():
        idx, result = result_queue.get()
        results[idx] = result

    return results


# ══════════════════════════════════════════════════════════════
# Main Execute
# ══════════════════════════════════════════════════════════════

def execute(params: dict) -> dict:
    agents = params.get("agents", [])
    timeout = int(params.get("timeout", 120))

    # Legacy: tasks als Shell-Commands
    if not agents and "tasks" in params:
        agents = [{"role": "executor", "task": t} for t in params["tasks"]]

    # Auto-planning: Brain entscheidet welche Agenten gebraucht werden
    if not agents and "task" in params:
        agents = _plan_agents(params["task"])

    if not agents:
        return {
            "success": False,
            "result": "No agents defined. Use: {agents: [{role, task}]} or {task: 'description'}",
        }
    if len(agents) > 8:
        return {"success": False, "result": "Max 8 parallel agents allowed"}

    log.info(f"Spawning {len(agents)} agents: {[a.get('role','?') for a in agents]}")

    # Shared Memory für diesen Run erstellen
    shared_mem = AgentSharedMemory()

    # DAG-aware Execution: Gruppen identifizieren
    groups = _identify_execution_groups(agents)
    log.info(f"Execution plan: {len(groups)} group(s): {groups}")

    all_results = {}

    for group_idx, group in enumerate(groups):
        roles_in_group = [agents[i].get("role", "?") for i in group]
        log.info(
            f"Group {group_idx+1}/{len(groups)}: "
            f"Running {len(group)} agent(s) in parallel: {roles_in_group}"
        )

        group_results = _execute_agent_group(agents, group, timeout, shared_mem)
        all_results.update(group_results)

        # Kurze Pause zwischen Gruppen für API Rate Limits
        if group_idx < len(groups) - 1:
            time.sleep(0.5)

    # Ergebnisse zusammenstellen
    results = []
    for i in range(len(agents)):
        results.append(
            all_results.get(i, {
                "role": agents[i].get("role", "?"),
                "task": agents[i].get("task", "?"),
                "status": "timeout",
                "output": "Agent timed out",
                "duration": timeout,
            })
        )

    success_count = sum(1 for r in results if r["status"] == "ok")
    total_duration = max((r.get("duration", 0) for r in results), default=0)

    parts = [
        f"Multi-Agent: {success_count}/{len(agents)} succeeded "
        f"(parallel wall-time: {total_duration:.1f}s)\n"
        f"Execution: {len(groups)} group(s), DAG-ordered\n"
    ]
    for i, r in enumerate(results):
        icon = "✅" if r["status"] == "ok" else "❌"
        deps = agents[i].get("depends_on", [])
        dep_str = f" (depends: {deps})" if deps else ""
        parts.append(
            f"{icon} [{r['role'].upper()}]{dep_str} ({r.get('duration',0):.1f}s)\n"
            f"Task: {r['task'][:100]}\n"
            f"Output: {r['output'][:800]}\n"
        )

    # ── DeepThink Review (fix: benutzt jetzt review_multi_agent) ──
    deepthink_review = ""
    if (
        _brain
        and hasattr(_brain, "deepthink")
        and _brain.deepthink
        and _brain.deepthink.is_enabled()
    ):
        try:
            all_outputs = ""
            for i, r in enumerate(results):
                all_outputs += f"\n[{r['role'].upper()}]: {r['output'][:500]}"

            task_desc = params.get("task", agents[0].get("task", "") if agents else "")

            review = _brain.deepthink.review_multi_agent(task_desc, all_outputs)

            status = "✅" if review.get("approved") else "⚠️"
            deepthink_review = (
                f"\n{'='*50}\n"
                f"{status} DEEPTHINK REVIEW\n"
                f"Feedback: {review.get('feedback', '')}\n"
                f"Summary: {review.get('summary', '')}"
            )
            log.info(f"DeepThink review done: approved={review.get('approved')}")
        except Exception as e:
            log.warning(f"DeepThink review failed: {e}")

    # Shared Memory aufräumen
    shared_mem.clear()

    return {
        "success": success_count > 0,
        "result": "\n".join(parts) + deepthink_review,
        "details": results,
        "success_count": success_count,
        "total_agents": len(agents),
        "execution_groups": len(groups),
        "parallel_duration": total_duration,
    }
