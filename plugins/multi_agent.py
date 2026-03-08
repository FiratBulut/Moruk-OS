"""
Moruk AI OS - Multi-Agent Orchestrator
Spawnt parallele KI-Agenten mit spezifischen Rollen.

Rollen:
  researcher  — Recherchiert/analysiert, gibt strukturierte Infos zurück
  coder       — Schreibt/editiert Code-Dateien
  writer      — Erstellt Texte, Docs, Summaries
  reviewer    — Reviewed Output anderer Agenten
  executor    — Führt Shell-Befehle aus (original multi_agent behavior)
"""

PLUGIN_NAME = "multi_agent"
PLUGIN_DESCRIPTION = (
    "Spawn parallel AI agents with specific roles (researcher, coder, writer, reviewer). "
    "Use for: research+write+review simultaneously, parallel code tasks, multi-perspective analysis."
)
PLUGIN_PARAMS = (
    '"agents": [{"role": "researcher|coder|writer|reviewer|executor", '
    '"task": "what to do", "context": "optional extra context"}], '
    '"timeout": 120'
)
PLUGIN_CORE = False

import threading
import queue
import subprocess
import shlex
import os
import time
from core.logger import get_logger

log = get_logger("multi_agent")

# Von ToolRouter gesetzt
_brain = None

ROLE_PROMPTS = {
    "researcher": (
        "You are a Research Agent. Gather, analyze and structure information. "
        "Use web_search, read_file, file_manager. End with a clear SUMMARY section."
    ),
    "coder": (
        "You are a Coding Agent. Write, edit and test code. "
        "Always use write_file or self_edit to save. Run syntax checks after writing .py files. "
        "End with a summary of files created/modified."
    ),
    "writer": (
        "You are a Writer Agent. Create clear, well-structured text content. "
        "Use write_file to save documents. End with a summary of what was created."
    ),
    "reviewer": (
        "You are a Review Agent. Critically evaluate work. Look for bugs, inconsistencies, quality issues. "
        "Return: APPROVED/REJECTED, Issues list, Suggestions."
    ),
    "executor": (
        "You are an Execution Agent. Run shell commands via terminal tool. Report exact output."
    ),
}


def _run_agent(agent_def: dict, result_queue: queue.Queue, idx: int, timeout: int):
    role = agent_def.get("role", "executor")
    task = agent_def.get("task", "")
    context = agent_def.get("context", "")
    start_time = time.time()

    try:
        if role == "executor":
            try:
                args = shlex.split(task)
                out = subprocess.check_output(
                    args, shell=False, timeout=timeout,
                    stderr=subprocess.STDOUT,
                    cwd=os.path.expanduser("~/moruk-os")
                )
                output = out.decode(errors="replace").strip()[:2000]
                status = "ok"
            except Exception as e:
                output = str(e)
                status = "error"

            result_queue.put((idx, {
                "role": role, "task": task, "status": status,
                "output": output, "duration": round(time.time() - start_time, 1)
            }))
            return

        if _brain is None:
            result_queue.put((idx, {
                "role": role, "task": task, "status": "error",
                "output": "Brain not connected to multi_agent plugin",
                "duration": 0
            }))
            return

        role_system = ROLE_PROMPTS.get(role, ROLE_PROMPTS["executor"])
        full_task = f"{task}\n\nExtra Context:\n{context}" if context else task

        response = _brain.think(
            full_task,
            extra_context=f"[AGENT ROLE: {role.upper()}]\n{role_system}",
            max_iterations=12,
            depth=3,
            isolated=True
        )

        result_queue.put((idx, {
            "role": role, "task": task, "status": "ok",
            "output": (response or "(no output)")[:3000],
            "duration": round(time.time() - start_time, 1)
        }))

    except Exception as e:
        result_queue.put((idx, {
            "role": role, "task": task, "status": "error",
            "output": f"Agent error: {e}",
            "duration": round(time.time() - start_time, 1)
        }))


def execute(params: dict) -> dict:
    agents = params.get("agents", [])
    timeout = int(params.get("timeout", 120))

    # Legacy: tasks als Shell-Commands
    if not agents and "tasks" in params:
        agents = [{"role": "executor", "task": t} for t in params["tasks"]]

    if not agents:
        return {"success": False, "result": "No agents defined. Use: {agents: [{role, task}]}"}
    if len(agents) > 8:
        return {"success": False, "result": "Max 8 parallel agents allowed"}

    log.info(f"Spawning {len(agents)} agents: {[a.get('role','?') for a in agents]}")

    result_queue = queue.Queue()
    threads = []

    for i, agent_def in enumerate(agents):
        t = threading.Thread(
            target=_run_agent,
            args=(agent_def, result_queue, i, timeout),
            daemon=True
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=timeout + 5)

    raw_results = {}
    while not result_queue.empty():
        idx, result = result_queue.get()
        raw_results[idx] = result

    results = [raw_results.get(i, {
        "role": agents[i].get("role", "?"),
        "task": agents[i].get("task", "?"),
        "status": "timeout",
        "output": "Agent timed out",
        "duration": timeout
    }) for i in range(len(agents))]

    success_count = sum(1 for r in results if r["status"] == "ok")
    total_duration = max((r.get("duration", 0) for r in results), default=0)

    parts = [
        f"Multi-Agent: {success_count}/{len(agents)} succeeded "
        f"(parallel wall-time: {total_duration:.1f}s)\n"
    ]
    for i, r in enumerate(results):
        icon = "✅" if r["status"] == "ok" else "❌"
        parts.append(
            f"{icon} [{r['role'].upper()}] ({r.get('duration',0):.1f}s)\n"
            f"Task: {r['task'][:100]}\n"
            f"Output: {r['output'][:800]}\n"
        )

    return {
        "success": success_count > 0,
        "result": "\n".join(parts),
        "details": results,
        "success_count": success_count,
        "parallel_duration": total_duration
    }
