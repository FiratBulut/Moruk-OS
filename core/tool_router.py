"""
Moruk AI OS - Tool Router v2.1
Handles extraction and execution of tool calls from AI responses.

v2.1 Änderungen:
- Reflector wird nach jeder Tool-Ausführung aufgerufen (auto_reflect_tool)
- Kein DeepThink import mehr (brain.py macht das Auditing)
- _autonomy_loop Referenz sauberer gelöst
"""

import json
import re

from core.executor import Executor
from core.memory import Memory
from core.plugin_manager import PluginManager
from core.self_model import SelfModel
from core.task_manager import TaskManager


def sanitize_for_json(text: str) -> str:
    if not text:
        return ""
    text = re.compile(r"\x1b\[[0-9;]*[mGKHF]?").sub("", text)
    text = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]").sub("", text)
    lines = text.split("\n")
    if len(lines) > 500:
        text = (
            "\n".join(lines[:250])
            + "\n\n... [TRUNCATED] ...\n\n"
            + "\n".join(lines[-250:])
        )
    return text


class ToolRouter:
    """
    Handles extraction and execution of tool calls from AI responses.
    Supports <tool> and <tool_call> tags with JSON or shorthand format.
    """

    TOOL_BLOCK_PATTERN = re.compile(r"<(tool(?:_call)?)>(.*?)</\1>", re.DOTALL)

    def __init__(self, executor: Executor, task_manager: TaskManager, memory: Memory):
        self.executor = executor
        self.tasks = task_manager
        self.memory = memory
        self.reflector = None
        self.plugin_manager = PluginManager()
        self.self_model = SelfModel()
        self._brain_ref = None
        self._autonomy_loop = None

        self._connect_plugins()

    def _connect_plugins(self):
        """Dynamische Verknüpfung von Core-Instanzen an Plugins."""
        lt_module = self.plugin_manager.plugins.get("list_tools")
        if lt_module is not None:
            lt_module._plugin_manager = self.plugin_manager

        if self._brain_ref:
            for plugin_name, module in self.plugin_manager.plugins.items():
                if hasattr(module, "_brain"):
                    module._brain = self._brain_ref

    def set_brain(self, brain):
        """Brain-Referenz setzen — wird von MainWindow nach __init__ aufgerufen."""
        self._brain_ref = brain
        self._connect_plugins()

    def set_autonomy_loop(self, loop):
        """AutonomyLoop-Referenz für start_project Tool."""
        self._autonomy_loop = loop

    def extract_tool_calls(self, response: str) -> list:
        calls = []
        for match in self.TOOL_BLOCK_PATTERN.finditer(response):
            content = match.group(2).strip()
            if not content:
                continue

            # Attempt 1: Full JSON block
            try:
                data = json.loads(content)
                if isinstance(data, dict) and "tool" in data:
                    calls.append(data)
                    continue
            except json.JSONDecodeError:
                pass

            # Attempt 2: Shorthand format 'tool_name: {json_params}'
            if ":" in content:
                parts = content.split(":", 1)
                tool_name = parts[0].strip()
                params_str = parts[1].strip()

                if tool_name and params_str.startswith("{"):
                    try:
                        params = json.loads(params_str)
                        calls.append({"tool": tool_name, "params": params})
                    except json.JSONDecodeError:
                        pass

        return calls

    def has_tool_calls(self, response: str) -> bool:
        return bool(self.extract_tool_calls(response))

    def format_results(self, results: list) -> str:
        if not results:
            return ""
        formatted = []
        for res in results:
            if isinstance(res, str):
                res = {"tool": "unknown", "success": True, "result": res}
            elif not isinstance(res, dict):
                res = {"tool": "unknown", "success": True, "result": str(res)}

            res_copy = res.copy()
            if "result" in res_copy:
                res_copy["result"] = sanitize_for_json(str(res_copy["result"]))
            formatted.append(
                f"<tool_response>\n{json.dumps(res_copy, indent=2, ensure_ascii=False)}\n</tool_response>"
            )
        return "\n".join(formatted)

    def execute_tool(self, call: dict, user_message: str = "") -> dict:
        """Executes a single tool call and runs reflection."""
        tool = call.get("tool", "")
        params = call.get("params", {})

        result = self._execute_tool_internal(tool, params)

        # v2.1: Reflector nach jeder Tool-Ausführung
        if self.reflector and hasattr(self.reflector, "auto_reflect_tool"):
            try:
                self.reflector.auto_reflect_tool(tool, params, result)
            except Exception:
                pass  # Reflection darf nie die Tool-Execution blockieren

        return result

    def _execute_tool_internal(self, tool: str, params: dict) -> dict:
        """Interne Tool-Ausführung ohne Reflection."""
        try:
            # ── Core Tools ────────────────────────────────────────
            if tool == "terminal":
                return self.executor.run_command(params.get("command", ""))

            elif tool == "read_file":
                return self.executor.read_file(params.get("path", ""))

            elif tool in ("write_file", "self_edit"):
                path = params.get("path", "")
                result = self.executor.write_file(path, params.get("content", ""))

                # Hot-Reload für Plugins
                if (
                    result.get("success")
                    and "plugins/" in path
                    and path.endswith(".py")
                ):
                    try:
                        self.plugin_manager.reload_all()
                        self._connect_plugins()
                        result["result"] = str(result.get("result", "")) + " | Plugin hot-reloaded"
                    except Exception as e:
                        result["result"] = str(result.get("result", "")) + f" | Hot-reload failed: {e}"

                return result

            # ── Task Management ───────────────────────────────────
            elif tool in ("task_create", "create_task"):
                t = self.tasks.add_task(
                    params.get("title", "Untitled"),
                    description=params.get("description", ""),
                    priority=params.get("priority", "normal"),
                )
                return {
                    "tool": tool,
                    "success": True,
                    "result": f"Task created: {t['id']}",
                }

            elif tool in ("task_complete", "complete_task"):
                task_id = params.get("task_id", "")
                result_text = params.get("result", "Completed")

                if not task_id:
                    active = self.tasks.get_next_task()
                    if active:
                        task_id = active["id"]

                if task_id:
                    self.tasks.complete_task(task_id)
                    return {
                        "tool": tool,
                        "success": True,
                        "result": f"Task {task_id} completed: {result_text}",
                    }
                return {
                    "tool": tool,
                    "success": False,
                    "result": "No task_id provided and no active task found",
                }

            elif tool in ("task_fail", "fail_task"):
                task_id = params.get("task_id", "")
                reason = params.get("reason", "Failed")
                if task_id:
                    self.tasks.fail_task(task_id)
                    return {
                        "tool": tool,
                        "success": True,
                        "result": f"Task {task_id} marked failed: {reason}",
                    }
                return {"tool": tool, "success": False, "result": "No task_id provided"}

            # ── Memory ────────────────────────────────────────────
            elif tool == "memory_store":
                content = params.get("content", "")
                category = params.get("category", "general")
                tags = params.get("tags", [])

                personal_keywords = (
                    "liebling", "favorite", "mag ", "mag keine", "liebe ", "hasse ",
                    "mein name", "my name", "ich bin", "i am", "ich arbeite", "i work",
                    "mein job", "my job", "mein hobby", "my hobby", "ich wohne", "i live",
                    "meine familie", "my family", "ich heiße", "mein alter", "my age",
                    "ich esse", "i eat", "ich trinke", "i drink", "mein lieblings",
                    "ich spiele", "ich lese", "mein beruf", "ich mag",
                )

                if any(kw in content.lower() for kw in personal_keywords):
                    category = "personal"

                self.memory.remember_long(content, category=category, tags=tags)
                return {
                    "tool": "memory_store",
                    "success": True,
                    "result": "Stored in long-term memory",
                }

            elif tool == "memory_search":
                query = params.get("query", "")
                results = self.memory.get_memory_context(query=query)
                return {
                    "tool": tool,
                    "success": True,
                    "result": results or "No results",
                }

            # ── Project Manager ───────────────────────────────────
            elif tool == "start_project":
                if self._autonomy_loop:
                    prompt = params.get("prompt", "")
                    self._autonomy_loop.queue_project(prompt)
                    return {
                        "tool": tool,
                        "success": True,
                        "result": f"Project queued: {prompt[:60]}",
                    }
                return {
                    "tool": tool,
                    "success": False,
                    "result": "Autonomy loop not available",
                }

            # ── Plugins ───────────────────────────────────────────
            elif self.plugin_manager.has_plugin(tool):
                try:
                    result = self.plugin_manager.execute(tool, params)
                    if isinstance(result, dict) and "result" in result:
                        result["result"] = str(result["result"])[:5000]
                    return result
                except Exception as plugin_e:
                    return {
                        "tool": tool,
                        "success": False,
                        "result": f"Plugin error: {plugin_e}",
                    }

            return {
                "tool": tool,
                "success": False,
                "result": f"Unknown tool: '{tool}'. Available: terminal, read_file, write_file, "
                          f"task_complete, task_create, memory_store, memory_search, start_project + plugins",
            }

        except Exception as e:
            return {
                "tool": tool,
                "success": False,
                "result": f"Tool error: {type(e).__name__}: {e}",
            }
