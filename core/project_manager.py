"""
Moruk AI OS - Project Manager v2
Orchestriert große Projekte: DeepThink zerlegt → Small Model arbeitet ab → DeepThink reviewed.
Workflow: Decompose → Execute Subtasks → Review Each → Final Review

v2 Änderungen:
- execute_next_subtask() entfernt (war toter Code, identisch mit _execute_single_subtask)
- Parallel-Execution nutzt _execute_single_subtask direkt
- Reflector-Integration für Post-Project-Learning
- Cleaner error handling
"""

import json
import time
import threading
import queue
from typing import Optional, Callable
from core.logger import get_logger

log = get_logger("project_manager")


# ── Prompts ──────────────────────────────────────────────────

DECOMPOSE_PROMPT = """You are a senior software architect. Break down the following project request into concrete, ordered subtasks.

PROJECT REQUEST:
{user_prompt}

EXISTING CODEBASE CONTEXT:
{codebase_context}

Rules:
- Each subtask must be a single, atomic unit of work (one file, one function, one fix).
- Order subtasks by dependency (what must be built first).
- Include a clear "done criteria" for each subtask so a reviewer knows when it's complete.
- If the project requires modifying existing files, specify WHICH file and WHAT to change.
- Keep subtasks between 3-10. If the project is bigger, group logically.
- IMPORTANT: Use the "depends_on" array to list the 0-based indices of any previous subtasks that MUST be completed before this subtask can start. If it has no dependencies, leave the array empty [].

Respond ONLY with a JSON object (no markdown, no extra text):
{{
  "project_title": "Short title for the project",
  "project_summary": "1-2 sentence summary",
  "subtasks": [
    {{
      "title": "Subtask title",
      "description": "Detailed description of what to do",
      "done_criteria": "How to verify this subtask is complete",
      "files_involved": ["path/to/file.py"],
      "priority": "high",
      "depends_on": []
    }}
  ]
}}
"""

SUBTASK_REVIEW_PROMPT = """You are a strict code reviewer. Review the execution result of this subtask.

PROJECT: {project_title}
SUBTASK: {subtask_title}
DESCRIPTION: {subtask_description}
DONE CRITERIA: {done_criteria}

EXECUTION RESULT:
{execution_result}

Evaluate:
1. Was the subtask completed according to the done criteria?
2. Are there any bugs, issues, or missing pieces?
3. Is the code quality acceptable?

Respond ONLY with a JSON object (no markdown, no extra text):
{{
  "approved": true/false,
  "confidence": 0.0-1.0,
  "issues": ["issue1", "issue2"],
  "feedback": "What needs to be fixed (only if not approved)",
  "notes": "Any observations for the next subtask"
}}
"""

FINAL_REVIEW_PROMPT = """You are a senior software architect doing a final review of a completed project.

PROJECT: {project_title}
PROJECT SUMMARY: {project_summary}

SUBTASK RESULTS:
{all_results}

Review the entire project:
1. Does everything fit together?
2. Are there integration issues between subtasks?
3. Is anything missing that was in the original request?
4. Are there any security or stability concerns?

Respond ONLY with a JSON object (no markdown, no extra text):
{{
  "approved": true/false,
  "confidence": 0.0-1.0,
  "issues": ["issue1", "issue2"],
  "integration_notes": "Notes about how subtasks fit together",
  "missing": ["anything missing from original request"],
  "final_verdict": "Ship it / Needs fixes / Major rework needed"
}}
"""


class ProjectManager:
    """Orchestriert Projekte: Decompose → Execute → Review → Final Review."""

    MAX_RETRIES_PER_SUBTASK = 2

    def __init__(self, brain, deepthink, task_manager, reflector=None):
        self.brain = brain
        self._connect_multi_agent(brain)
        self.deepthink = deepthink
        self.tasks = task_manager
        self.reflector = reflector

        # State
        self.active_project = None
        self.is_running = False
        self._current_task_id = None  # Für Delete-Check von außen

        # Callbacks für UI-Updates
        self.on_status: Optional[Callable] = None
        self.on_thought: Optional[Callable] = None
        self.on_subtask_start: Optional[Callable] = None
        self.on_subtask_done: Optional[Callable] = None
        self.on_project_done: Optional[Callable] = None

    def _connect_multi_agent(self, brain):
        """Verbindet Brain mit multi_agent Plugin."""
        try:
            from plugins import multi_agent as ma
            ma._brain = brain
        except Exception:
            try:
                import importlib.util, pathlib
                p = pathlib.Path(__file__).parent.parent / "plugins" / "multi_agent.py"
                if p.exists():
                    spec = importlib.util.spec_from_file_location("multi_agent", p)
                    ma = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(ma)
                    ma._brain = brain
            except Exception as e:
                log.warning(f"multi_agent brain connect failed: {e}")

    def _emit_status(self, msg: str):
        log.info(f"[PM] {msg}")
        if self.on_status:
            self.on_status(msg)

    def _emit_thought(self, msg: str):
        log.info(f"[PM] 💭 {msg}")
        if self.on_thought:
            self.on_thought(msg)

    # ── Phase 1: Decompose ───────────────────────────────────

    def decompose(self, user_prompt: str, codebase_context: str = "") -> Optional[dict]:
        """DeepThink zerlegt den User-Prompt in Subtasks."""
        self._emit_status("🧠 DeepThink: Analyzing project...")

        prompt = DECOMPOSE_PROMPT.format(
            user_prompt=user_prompt,
            codebase_context=codebase_context or "No additional context.",
        )

        if self.deepthink and self.deepthink.is_enabled():
            raw = self.deepthink.think(prompt)
        else:
            self._emit_thought("DeepThink nicht aktiv — verwende Brain für Decompose")
            raw = self.brain.think(prompt, isolated=True)

        plan = self._parse_json(raw)
        if not plan or "subtasks" not in plan:
            log.error(f"Decompose failed. Raw: {(raw or '')[:500]}")
            self._emit_thought("❌ Konnte Projekt nicht zerlegen — ungültiges JSON")
            return None

        subtasks = plan["subtasks"]
        if not subtasks:
            self._emit_thought("❌ Keine Subtasks generiert")
            return None

        self._emit_status(f"📋 Projekt zerlegt: {len(subtasks)} Subtasks")
        for i, st in enumerate(subtasks, 1):
            self._emit_thought(f"  [{i}] {st['title']}")

        return plan

    # ── Phase 2: Create Tasks ────────────────────────────────

    def create_project_tasks(self, plan: dict) -> dict:
        """Erstellt Parent-Task + Subtasks im TaskManager."""
        parent = self.tasks.add_task(
            title=f"🏗 {plan['project_title']}",
            description=plan.get("project_summary", ""),
            priority="high",
        )
        parent_id = parent["id"]
        self._current_task_id = parent_id

        subtask_ids = []
        for i, st in enumerate(plan["subtasks"]):
            sub = self.tasks.add_task(
                title=f"[{i+1}/{len(plan['subtasks'])}] {st['title']}",
                description=st.get("description", ""),
                priority=st.get("priority", "normal"),
                parent_id=parent_id,
            )
            subtask_ids.append(sub["id"])
            self.tasks.add_subtask_id(parent_id, sub["id"])

        project = {
            "plan": plan,
            "parent_id": parent_id,
            "subtask_ids": subtask_ids,
            "results": {},
            "reviews": {},
            "current_index": 0,
            "status": "ready",
        }

        self.active_project = project
        self._emit_status(
            f"✅ Projekt erstellt: {plan['project_title']} ({len(subtask_ids)} Subtasks)"
        )
        return project

    # ── Phase 3: Execute Subtasks ────────────────────────────

    def _execute_single_subtask(
        self, idx: int, on_tool_start=None, on_tool_result=None
    ) -> dict:
        """Führt einen einzelnen Subtask aus (mit Retry-Logik)."""
        if not self.active_project:
            return {"approved": False, "error": "No active project"}

        proj = self.active_project
        subtask_id = proj["subtask_ids"][idx]
        plan_subtask = proj["plan"]["subtasks"][idx]

        self._emit_status(
            f"🔧 Subtask {idx+1}/{len(proj['subtask_ids'])}: {plan_subtask['title']}"
        )
        if self.on_subtask_start:
            self.on_subtask_start(idx, plan_subtask)

        # Prüfe ob Task noch existiert (könnte gelöscht worden sein)
        if not self.tasks.get_task_by_id(subtask_id):
            log.warning(f"Subtask [{subtask_id}] wurde gelöscht — überspringe")
            return {"approved": False, "error": "Task deleted"}

        self.tasks.update_status(subtask_id, "active")

        # Kontext aus vorherigen Reviews
        previous_notes = ""
        for prev_id, review in proj["reviews"].items():
            if review.get("notes"):
                previous_notes += f"- {review['notes']}\n"

        context = f"""PROJECT MODE - Subtask {idx+1}/{len(proj['subtask_ids'])}.

Project: {proj['plan']['project_title']}
Current Subtask: {plan_subtask['title']}
Description: {plan_subtask.get('description', '')}
Done Criteria: {plan_subtask.get('done_criteria', 'Complete as described')}
Files Involved: {', '.join(plan_subtask.get('files_involved', []))}

{"Notes from previous reviews:\n" + previous_notes if previous_notes else ""}

CRITICAL FILE RULES:
- ALWAYS use the EXACT file paths listed in "Files Involved" above
- NEVER create duplicate files or alternative versions in other locations
- If a file already exists: read it first, then modify — do NOT start from scratch
- All subtasks write to the SAME files — check what exists before writing

INSTRUCTIONS: Complete FULLY. Use tools. When done, explain what files were changed.
Do NOT ask questions. Focus only on THIS subtask.
"""

        retries = 0
        while retries <= self.MAX_RETRIES_PER_SUBTASK:
            try:
                response = self.brain.think(
                    f"[PROJECT] Execute: {plan_subtask['title']}",
                    extra_context=context,
                    on_tool_start=on_tool_start,
                    on_tool_result=on_tool_result,
                    max_iterations=10,
                    depth=3,
                    isolated=True,
                )

                proj["results"][subtask_id] = response
                review = self._review_subtask(plan_subtask, response)
                proj["reviews"][subtask_id] = review

                if review.get("approved", False):
                    self.tasks.complete_task(subtask_id)
                    self._emit_status(f"✅ Subtask {idx+1} approved")
                    if self.on_subtask_done:
                        self.on_subtask_done(idx, "approved", review)
                    proj["current_index"] = max(proj["current_index"], idx + 1)
                    return review
                else:
                    retries += 1
                    feedback = review.get("feedback", "No specific feedback")
                    if retries > self.MAX_RETRIES_PER_SUBTASK:
                        self.tasks.fail_task(subtask_id)
                        self._emit_status(
                            f"❌ Subtask {idx+1} failed after {retries} attempts"
                        )
                        if self.on_subtask_done:
                            self.on_subtask_done(idx, "failed", review)
                        proj["current_index"] = max(proj["current_index"], idx + 1)
                        return review
                    context += f"\n\nREVISION (Attempt {retries+1}):\nFeedback: {feedback}\nFix these issues."

            except Exception as e:
                log.error(f"Subtask {idx} error: {e}", exc_info=True)
                retries += 1
                if retries > self.MAX_RETRIES_PER_SUBTASK:
                    self.tasks.fail_task(subtask_id)
                    proj["current_index"] = max(proj["current_index"], idx + 1)
                    return {"approved": False, "error": str(e)}

        return {"approved": False, "error": "Max retries exceeded"}

    def _execute_subtask_thread(
        self, idx: int, result_queue: queue.Queue,
        on_tool_start=None, on_tool_result=None,
    ):
        """Thread-Wrapper für parallele Subtask-Execution."""
        try:
            review = self._execute_single_subtask(idx, on_tool_start, on_tool_result)
            result_queue.put((idx, review))
        except Exception as e:
            result_queue.put((idx, {"approved": False, "error": str(e)}))

    def _identify_parallel_groups(self, subtasks: list) -> list:
        """Topological Sort — gruppiert Subtasks nach Abhängigkeiten."""
        n = len(subtasks)
        groups = []
        completed = set()
        remaining = list(range(n))

        for _ in range(n):
            if not remaining:
                break
            ready = []
            still_waiting = []
            for idx in remaining:
                deps = subtasks[idx].get("depends_on", [])
                if all(d in completed for d in deps):
                    ready.append(idx)
                else:
                    still_waiting.append(idx)

            if not ready:
                log.warning(
                    f"Circular dependency detected, running {still_waiting} sequentially"
                )
                for i in still_waiting:
                    groups.append([i])
                break

            # Max 3 parallel (API Load)
            for batch_start in range(0, len(ready), 3):
                groups.append(ready[batch_start : batch_start + 3])
            for idx in ready:
                completed.add(idx)
            remaining = still_waiting

        return groups

    def execute_parallel_group(
        self, group: list, on_tool_start=None, on_tool_result=None
    ) -> list:
        """Führt eine Gruppe von Subtasks parallel aus."""
        if len(group) == 1:
            review = self._execute_single_subtask(
                group[0], on_tool_start, on_tool_result
            )
            return [review]

        self._emit_status(f"⚡ Parallel: {len(group)} Subtasks gleichzeitig...")
        result_queue = queue.Queue()
        threads = []

        for idx in group:
            t = threading.Thread(
                target=self._execute_subtask_thread,
                args=(idx, result_queue, on_tool_start, on_tool_result),
                daemon=True,
            )
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=300)

        reviews = {}
        while not result_queue.empty():
            idx, review = result_queue.get()
            reviews[idx] = review

        return [
            reviews.get(i, {"approved": False, "error": "Thread timeout"})
            for i in group
        ]

    def _review_subtask(self, plan_subtask: dict, execution_result: str) -> dict:
        """DeepThink reviewed einen Subtask."""
        proj = self.active_project
        if not proj:
            return {"approved": True, "confidence": 0.5}

        self._emit_status("🧠 DeepThink: Reviewing subtask...")

        prompt = SUBTASK_REVIEW_PROMPT.format(
            project_title=proj["plan"]["project_title"],
            subtask_title=plan_subtask["title"],
            subtask_description=plan_subtask.get("description", ""),
            done_criteria=plan_subtask.get("done_criteria", "N/A"),
            execution_result=execution_result[:4000],
        )

        if self.deepthink and self.deepthink.is_enabled():
            raw = self.deepthink.think(prompt)
        else:
            raw = self.brain.think(prompt, isolated=True)

        result = self._parse_json(raw)
        if not result:
            log.warning(
                f"Subtask review parse failed, defaulting to approved. Raw: {(raw or '')[:300]}"
            )
            return {
                "approved": True,
                "confidence": 0.5,
                "issues": [],
                "feedback": "",
                "notes": "",
            }

        return result

    # ── Phase 4: Final Review ────────────────────────────────

    def final_review(self) -> dict:
        """DeepThink macht Gesamtreview nach allen Subtasks."""
        if not self.active_project:
            return {"approved": False, "error": "No active project"}

        proj = self.active_project
        self._emit_status("🧠 DeepThink: Final project review...")

        all_results = []
        for i, subtask_id in enumerate(proj["subtask_ids"]):
            plan_st = proj["plan"]["subtasks"][i]
            result = proj["results"].get(subtask_id, "No result")
            review = proj["reviews"].get(subtask_id, {})
            status = "✅ APPROVED" if review.get("approved") else "❌ FAILED"

            all_results.append(
                f"--- Subtask {i+1}: {plan_st['title']} [{status}] ---\n"
                f"Result: {str(result)[:500]}\n"
                f"Review: {json.dumps(review, ensure_ascii=False)[:300]}\n"
            )

        prompt = FINAL_REVIEW_PROMPT.format(
            project_title=proj["plan"]["project_title"],
            project_summary=proj["plan"].get("project_summary", ""),
            all_results="\n".join(all_results),
        )

        if self.deepthink and self.deepthink.is_enabled():
            raw = self.deepthink.think(prompt)
        else:
            raw = self.brain.think(prompt, isolated=True)

        result = self._parse_json(raw)
        if not result:
            log.warning(f"Final review parse failed. Raw: {(raw or '')[:500]}")
            result = {
                "approved": True,
                "confidence": 0.5,
                "final_verdict": "Parse error — defaulting to approve",
            }

        # Parent Task Status setzen
        if result.get("approved", False):
            self.tasks.complete_task(proj["parent_id"])
            self._emit_status(
                f"🎉 Projekt abgeschlossen: {proj['plan']['project_title']}"
            )
        else:
            self._emit_status(
                f"⚠ Projekt needs fixes: {result.get('final_verdict', 'Unknown')}"
            )

        if self.on_project_done:
            self.on_project_done(result)

        return result

    # ── Full Pipeline ────────────────────────────────────────

    def run_project(
        self,
        user_prompt: str,
        codebase_context: str = "",
        on_tool_start=None,
        on_tool_result=None,
    ) -> dict:
        """Führt das komplette Projekt-Pipeline aus."""
        self.is_running = True

        try:
            # Phase 1: Decompose
            plan = self.decompose(user_prompt, codebase_context)
            if not plan:
                self.is_running = False
                return {"success": False, "error": "Decompose failed"}

            # Phase 2: Create Tasks
            project = self.create_project_tasks(plan)

            # Phase 3: Execute Subtasks (parallel wo möglich)
            project["status"] = "running"
            subtasks = plan["subtasks"]
            groups = self._identify_parallel_groups(subtasks)

            total_groups = len(groups)
            self._emit_status(
                f"🚀 Execution plan: {len(subtasks)} subtasks in {total_groups} group(s) "
                f"({'parallel' if any(len(g)>1 for g in groups) else 'sequential'})"
            )

            for group_idx, group in enumerate(groups):
                if not self.is_running:
                    self._emit_status("⏸ Projekt pausiert")
                    return {"success": False, "error": "Project paused"}

                # Prüfe ob Parent-Task noch existiert
                if not self.tasks.get_task_by_id(project["parent_id"]):
                    log.warning("Parent task deleted — aborting project")
                    self.is_running = False
                    return {"success": False, "error": "Project deleted"}

                if len(group) > 1:
                    titles = [subtasks[i]["title"][:30] for i in group]
                    self._emit_status(
                        f"⚡ Group {group_idx+1}/{total_groups}: "
                        f"Running {len(group)} subtasks in parallel: {titles}"
                    )
                else:
                    self._emit_status(
                        f"▶ Group {group_idx+1}/{total_groups}: "
                        f"{subtasks[group[0]]['title'][:50]}"
                    )

                self.execute_parallel_group(
                    group, on_tool_start=on_tool_start, on_tool_result=on_tool_result
                )
                time.sleep(0.3)

            # Phase 4: Final Review
            project["status"] = "reviewing"
            final = self.final_review()

            project["status"] = "completed" if final.get("approved") else "needs_fixes"
            self.active_project = project

            # Phase 5: Reflector Learning (NEU)
            if self.reflector:
                try:
                    subtask_reviews = list(project["reviews"].values())
                    self.reflector.reflect_on_project(
                        project_title=plan["project_title"],
                        subtask_results=subtask_reviews,
                        final_approved=final.get("approved", False),
                        final_verdict=final.get("final_verdict", ""),
                    )
                except Exception as e:
                    log.warning(f"Project reflection failed: {e}")

            self.is_running = False
            return {
                "success": final.get("approved", False),
                "project": project,
                "final_review": final,
            }

        except Exception as e:
            log.error(f"Project pipeline error: {e}", exc_info=True)
            self.is_running = False
            return {"success": False, "error": str(e)}

    def stop(self):
        self.is_running = False
        self._emit_status("⏹ Projekt gestoppt")

    # ── Helpers ──────────────────────────────────────────────

    def _parse_json(self, raw: str) -> Optional[dict]:
        import re

        if not raw:
            return None

        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        cleaned = (
            cleaned.removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)

        if cleaned and not cleaned.endswith("}"):
            cleaned = cleaned.rstrip(",") + "\n}"

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            log.warning(f"JSON parse failed: {e}. Raw: {cleaned[:300]}")
            return None

    def get_project_status(self) -> dict:
        if not self.active_project:
            return {"active": False}

        proj = self.active_project
        total = len(proj["subtask_ids"])
        done = proj["current_index"]
        approved = sum(1 for r in proj["reviews"].values() if r.get("approved"))
        failed = sum(1 for r in proj["reviews"].values() if not r.get("approved"))

        return {
            "active": True,
            "title": proj["plan"]["project_title"],
            "status": proj["status"],
            "total_subtasks": total,
            "completed": done,
            "approved": approved,
            "failed": failed,
            "progress": done / total if total > 0 else 0,
            "parent_id": proj["parent_id"],
        }
