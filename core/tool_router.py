import json
import os
import re
from pathlib import Path
from core.deepthink import DeepThink
from core.executor import Executor
from core.memory import Memory
from core.plugin_manager import PluginManager
from core.self_model import SelfModel
from core.task_manager import TaskManager

def sanitize_for_json(text: str) -> str:
    if not text: return ""
    # Remove ANSI escape sequences
    text = re.compile(r'\x1b\[[0-9;]*[mGKHF]?').sub('', text)
    # Remove non-printable control characters (except newline, tab, etc.)
    text = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]').sub('', text)
    lines = text.split('\n')
    if len(lines) > 500:
        text = '\n'.join(lines[:250]) + "\n\n... [TRUNCATED] ...\n\n" + '\n'.join(lines[-250:])
    return text

class ToolRouter:
    """
    Handles extraction and execution of tool calls from AI responses.
    Supports <tool> and <tool_call> tags with JSON or shorthand format.
    """
    # Matches both <tool> and <tool_call> blocks
    TOOL_BLOCK_PATTERN = re.compile(r'<(tool(?:_call)?)>(.*?)</\1>', re.DOTALL)

    def __init__(self, executor: Executor, task_manager: TaskManager, memory: Memory):
        self.executor = executor
        self.tasks = task_manager
        self.memory = memory
        self.reflector = None
        self.plugin_manager = PluginManager()
        self.self_model = SelfModel()
        self.deepthink = DeepThink()

        # list_tools Plugin mit PluginManager verbinden
        if self.plugin_manager.has_plugin("list_tools"):
            lt_module = self.plugin_manager.plugins.get("list_tools")
            if lt_module is not None:
                lt_module._plugin_manager = self.plugin_manager

        # multi_agent Plugin mit Brain verbinden (wird später von brain.py gesetzt)
        # brain wird in set_brain() gesetzt nach __init__
        self._brain_ref = None

    def set_brain(self, brain):
        """Brain-Referenz setzen — wird von brain.py nach __init__ aufgerufen."""
        self._brain_ref = brain
        # Plugins mit Brain verbinden
        for plugin_name in ("multi_agent", "summarizer"):
            module = self.plugin_manager.plugins.get(plugin_name)
            if module is not None and hasattr(module, "_brain"):
                module._brain = brain

    def extract_tool_calls(self, response: str) -> list:
        """
        Extracts tool calls from the response, supporting both <tool> and <tool_call> tags,
        standard JSON, and shorthand 'tool_name: {params}' format.
        Handles nested JSON objects within params.
        """
        calls = []
        for match in self.TOOL_BLOCK_PATTERN.finditer(response):
            content = match.group(2).strip()
            if not content: continue

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
                
                # Ensure tool_name looks like a valid identifier and params starts with {
                if tool_name and params_str.startswith("{"):
                    try:
                        params = json.loads(params_str)
                        calls.append({"tool": tool_name, "params": params})
                        continue
                    except json.JSONDecodeError:
                        pass
        
        return calls

    def has_tool_calls(self, response: str) -> bool:
        """
        Checks if the response contains any valid tool calls.
        """
        return len(self.extract_tool_calls(response)) > 0
    
    def format_results(self, results: list) -> str:
        """
        Formats tool execution results into <tool_response> tags for AI visibility.
        """
        if not results: return ""
        formatted = []
        for res in results:
            # res kann manchmal ein String sein statt Dict
            if isinstance(res, str):
                res = {"tool": "unknown", "success": True, "result": res}
            elif not isinstance(res, dict):
                res = {"tool": "unknown", "success": True, "result": str(res)}
            res_copy = res.copy()
            if "result" in res_copy:
                res_copy["result"] = sanitize_for_json(str(res_copy["result"]))
            formatted.append(f"<tool_response>\n{json.dumps(res_copy, indent=2, ensure_ascii=False)}\n</tool_response>")
        return "\n".join(formatted)

    def execute_tool(self, call: dict, user_message: str = "") -> dict:
        """
        Executes a single tool call through the appropriate handler.
        """
        tool = call.get("tool", "")
        params = call.get("params", {})
        try:
            # ── Core Tools ────────────────────────────────────────
            if tool == "terminal":
                return self.executor.run_command(params.get("command", ""))

            elif tool == "read_file":
                return self.executor.read_file(params.get("path", ""))

            elif tool in ("write_file", "self_edit"):
                path = params.get("path", "")
                result = self.executor.write_file(path, params.get("content", ""))

                # Hot-Reload: Neues Plugin sofort verfügbar ohne Neustart
                if result.get("success") and "plugins/" in path and path.endswith(".py"):
                    try:
                        self.plugin_manager.reload_all()
                        # list_tools nach reload neu verbinden
                        lt_module = self.plugin_manager.plugins.get("list_tools")
                        if lt_module is not None:
                            lt_module._plugin_manager = self.plugin_manager
                        # Brain-abhängige Plugins nach reload neu verbinden
                        for _pname in ("multi_agent", "summarizer"):
                            _pm = self.plugin_manager.plugins.get(_pname)
                            if _pm is not None and hasattr(_pm, "_brain") and self._brain_ref:
                                _pm._brain = self._brain_ref
                        result["result"] += " | Plugin hot-reloaded — sofort verfügbar"
                    except Exception as e:
                        result["result"] += f" | Hot-reload failed: {e}"

                return result

            # ── Task Management ───────────────────────────────────
            elif tool in ["task_create", "create_task"]:
                t = self.tasks.add_task(
                    params.get("title", "Untitled"),
                    description=params.get("description", ""),
                    priority=params.get("priority", "normal")
                )
                return {"tool": tool, "success": True, "result": f"Task created: {t['id']}"}

            elif tool in ["task_complete", "complete_task"]:
                # KRITISCH: Autonomy Loop braucht das um Tasks abzuschliessen
                task_id = params.get("task_id", "")
                result_text = params.get("result", "Completed")
                if not task_id:
                    # Fallback: aktiven Task suchen
                    active = self.tasks.get_next_task()
                    if active:
                        task_id = active["id"]
                if task_id:
                    self.tasks.complete_task(task_id)
                    return {"tool": tool, "success": True, "result": f"Task {task_id} completed: {result_text}"}
                return {"tool": tool, "success": False, "result": "No task_id provided and no active task found"}

            elif tool in ["task_fail", "fail_task"]:
                task_id = params.get("task_id", "")
                reason = params.get("reason", "Failed")
                if task_id:
                    self.tasks.fail_task(task_id)
                    return {"tool": tool, "success": True, "result": f"Task {task_id} marked failed: {reason}"}
                return {"tool": tool, "success": False, "result": "No task_id provided"}

            # ── Memory ────────────────────────────────────────────
            elif tool == "memory_store":
                content = params.get("content", "")
                category = params.get("category", "general")
                tags = params.get("tags", [])
                # Auto-detect personal info → save to user profile
                personal_keywords = [
                    "liebling", "favorite", "mag ", "mag keine", "liebe ", "hasse ",
                    "mein name", "my name", "ich bin", "i am", "ich arbeite", "i work",
                    "mein job", "my job", "mein hobby", "my hobby", "ich wohne", "i live",
                    "meine familie", "my family", "ich heiße", "mein alter", "my age",
                    "ich esse", "i eat", "ich trinke", "i drink", "mein lieblings",
                    "ich spiele", "ich lese", "mein beruf", "ich mag"
                ]
                content_lower = content.lower()
                if any(kw in content_lower for kw in personal_keywords):
                    category = "personal"
                self.memory.remember_long(content, category=category, tags=tags)
                return {"tool": "memory_store", "success": True, "result": "Stored in long-term memory"}

            elif tool == "memory_search":
                query = params.get("query", "")
                results = self.memory.get_memory_context(query=query)
                return {"tool": tool, "success": True, "result": results or "No results"}

            # ── Project Manager ───────────────────────────────────
            elif tool == "start_project":
                if hasattr(self, '_autonomy_loop') and self._autonomy_loop:
                    prompt = params.get("prompt", "")
                    self._autonomy_loop.queue_project(prompt)
                    return {"tool": tool, "success": True, "result": f"Project queued: {prompt[:60]}"}
                return {"tool": tool, "success": False, "result": "Autonomy loop not available"}

            # ── Plugins ───────────────────────────────────────────
            elif self.plugin_manager.has_plugin(tool):
                try:
                    result = self.plugin_manager.execute(tool, params)
                    # Plugin-Result auf 5000 Zeichen begrenzen
                    if isinstance(result, dict) and "result" in result:
                        result["result"] = str(result["result"])[:5000]
                    return result
                except Exception as plugin_e:
                    return {"tool": tool, "success": False, "result": f"Plugin error: {plugin_e}"}

            return {"tool": tool, "success": False, "result": f"Unknown tool: '{tool}'. Available: terminal, read_file, write_file, task_complete, task_create, memory_store, memory_search, start_project + plugins"}

        except Exception as e:
            return {"tool": tool, "success": False, "result": f"Tool error: {type(e).__name__}: {e}"}
