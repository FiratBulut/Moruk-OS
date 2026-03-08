from typing import Any
import json
import re
from pathlib import Path
from core.logger import get_logger
log = get_logger('deepthink')
DATA_DIR = Path(__file__).parent.parent / 'data'
REVIEW_SYSTEM_PROMPT = 'You are a strict AI supervisor. Your job is to review responses from a smaller AI model.\n\nEvaluate the response for:\n1. Correctness — Is the answer factually accurate and logically sound?\n2. Completeness — Does it fully address the user\'s request?\n3. Safety — Does it contain risky actions (e.g. file deletions, destructive commands) without justification?\n4. Clarity — Is it clear and not confusing or misleading?\n\nRespond ONLY with a JSON object in this exact format (no markdown, no extra text):\n{\n  "verdict": "approve" | "revise" | "reject",\n  "confidence": 0.0-1.0,\n  "issues": ["issue1", "issue2"],\n  "suggestion": "What the model should do differently (only if verdict is revise or reject)"\n}\n\nVerdicts:\n- approve: Response is good. No changes needed.\n- revise: Response has fixable issues. Provide a suggestion.\n- reject: Response is wrong, dangerous, or completely misses the point. You will answer directly instead.\n\nBe strict but fair. Only revise/reject when clearly necessary.'
DECOMPOSE_SYSTEM_PROMPT = 'You are a senior software architect. Your job is to break down project requests into concrete, ordered subtasks.\n\nRules:\n- Each subtask must be a single, atomic unit of work.\n- Order by dependency (what must be built first).\n- Include clear "done criteria" for each subtask.\n- If modifying existing files, specify WHICH file and WHAT to change.\n- Keep subtasks between 3-10.\n\nAlways respond ONLY with a JSON object (no markdown, no extra text).'
SUBTASK_REVIEW_SYSTEM_PROMPT = 'You are a strict code reviewer. Your job is to review the execution result of a subtask within a larger project.\n\nEvaluate:\n1. Was the subtask completed according to the done criteria?\n2. Are there bugs, issues, or missing pieces?\n3. Is the code quality acceptable?\n\nBe strict but fair. Approve if the core work is done correctly, even if minor improvements are possible.\n\nAlways respond ONLY with a JSON object (no markdown, no extra text).'

class DeepThink:
    """Supervisor Model für Validation, Deep Reasoning und Project Decomposition."""
    DEEP_THINK_PROMPT = 'Expert AI. Deep thinking mode. Step by step. Precise. {extra_context}'

    def __init__(self) -> None:
        self.client = None
        self.provider = None
        self.settings = {}
        self.enabled = False

    def configure(self, settings: dict) -> None:
        self.settings = settings
        provider = settings.get('deepthink_provider', '')
        api_key = settings.get('deepthink_api_key', '')
        model = settings.get('deepthink_model', '')
        if not provider or not api_key or (not model):
            self.enabled = False
            return
        try:
            if provider == 'anthropic':
                from anthropic import Anthropic
                self.client = Anthropic(api_key=api_key)
            else:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key, base_url=settings.get('deepthink_base_url'))
            self.provider = provider
            self.enabled = True
        except Exception as e:
            log.error(f'DeepThink init failed: {e}')
            self.enabled = False

    def is_enabled(self) -> bool:
        return self.enabled and self.client is not None

    def should_think_deep(self, user_message: str) -> bool:
        if not self.is_enabled():
            return False
        msg_lower = user_message.lower()
        return any((x in msg_lower for x in ['think deep', 'denk tief nach', 'tiefenanalyse']))

    def should_review(self, user_message: str, response: str, depth: int=3) -> bool:
        """Prüft ob die Antwort ein Reasoning-Review benötigt."""
        if not self.is_enabled():
            return False
        if depth >= 4:
            return True
        if 'self_edit' in response or 'terminal' in response:
            return True
        return False

    def should_review_tool(self, tool_call: dict) -> bool:
        """Prüft ob ein Tool-Aufruf ein Sicherheits-Review benötigt."""
        if not self.is_enabled():
            return False
        tool_name = tool_call.get('tool', '')
        return tool_name in ['terminal', 'write_file', 'self_edit', 'system_repair']

    def review(self, user_message: str, response: str) -> dict:
        """
        Supervisor-Review einer Haupt-Model-Antwort via DeepThink LLM.
        Gibt zurück: {"verdict": "approve"|"revise"|"reject", "confidence": float,
                      "issues": list, "suggestion": str}
        """
        if not self.is_enabled():
            return {'verdict': 'approve', 'confidence': 1.0, 'issues': [], 'suggestion': ''}
        model = self.settings.get('deepthink_model', '')
        user_content = f'USER REQUEST:\n{user_message}\n\nAI RESPONSE TO REVIEW:\n{response}'
        try:
            raw = self._call_llm(system=REVIEW_SYSTEM_PROMPT, user_content=user_content, model=model, max_tokens=1024, temperature=0.2)
            return self._parse_json_safe(raw, default={'verdict': 'approve', 'confidence': 0.5, 'issues': [], 'suggestion': ''})
        except Exception as e:
            log.error(f'DeepThink review error: {e}')
            return {'verdict': 'approve', 'confidence': 0.5, 'issues': [], 'suggestion': ''}

    def review_tool_call(self, tool_name: str, params: dict, user_message: str) -> dict:
        """Sicherheits-Shield für Tool-Aufrufe."""
        params_str = json.dumps(params).lower()
        forbidden = ['/core/', '/config/', '/moruk-os/core/', '/moruk-os/config/']
        if any((f in params_str for f in forbidden)):
            if tool_name == 'terminal':
                cmd = params.get('command', '').lstrip().lower()
                readonly_prefixes = ('grep', 'cat ', 'ls ', 'find ', 'head ', 'tail ', 'wc ', 'diff ', 'stat ', 'less ', 'more ')
                if cmd.startswith(readonly_prefixes):
                    return {'verdict': 'approve', 'approved': True}
                destructive = ['rm ', 'rm\t', 'mv ', '> ', '>> ', 'chmod', 'chown', 'truncate', 'shred', 'dd ', 'tee ']
                if any((x in cmd for x in destructive)):
                    return {'verdict': 'reject', 'approved': False, 'reason': 'Shield: Destruktive Befehle auf Systempfaden untersagt.'}
            elif tool_name in ('write_file', 'self_edit', 'system_repair'):
                return {'verdict': 'reject', 'approved': False, 'reason': f'Shield: Schreibzugriff auf System-Verzeichnisse via {tool_name} verweigert.'}
        return {'verdict': 'approve', 'approved': True}

    def decompose_project(self, user_prompt: str, codebase_context: str='') -> dict | None:
        """Zerlegt einen großen Projekt-Prompt in Subtasks.
        Returns: {"project_title": str, "project_summary": str, "subtasks": [...]}
        """
        if not self.is_enabled():
            log.warning('DeepThink not enabled for decompose_project')
            return None
        model = self.settings.get('deepthink_model', '')
        user_content = f'PROJECT REQUEST:\n{user_prompt}\n\nEXISTING CODEBASE CONTEXT:\n{codebase_context or 'No additional context.'}\n\nBreak this into ordered subtasks. Respond ONLY with JSON:\n{{"project_title": "...", "project_summary": "...", "subtasks": [{{"title": "...", "description": "...", "done_criteria": "...", "files_involved": ["..."], "priority": "high|normal|low"}}]}}'
        try:
            raw = self._call_llm(system=DECOMPOSE_SYSTEM_PROMPT, user_content=user_content, model=model, max_tokens=4096, temperature=0.3)
            result = self._parse_json_safe(raw, default=None)
            if result and 'subtasks' in result:
                log.info(f"Project decomposed: '{result.get('project_title', '?')}' → {len(result['subtasks'])} subtasks")
                return result
            log.warning(f'Decompose returned invalid structure. Raw: {raw[:500]}')
            return None
        except Exception as e:
            log.error(f'DeepThink decompose error: {e}')
            return None

    def review_subtask(self, project_title: str, subtask_title: str, subtask_description: str, done_criteria: str, execution_result: str) -> dict:
        """Reviewed das Ergebnis eines einzelnen Subtasks.
        Returns: {"approved": bool, "confidence": float, "issues": [...], "feedback": str, "notes": str}
        """
        default = {'approved': True, 'confidence': 0.5, 'issues': [], 'feedback': '', 'notes': ''}
        if not self.is_enabled():
            return default
        model = self.settings.get('deepthink_model', '')
        user_content = f'PROJECT: {project_title}\nSUBTASK: {subtask_title}\nDESCRIPTION: {subtask_description}\nDONE CRITERIA: {done_criteria}\n\nEXECUTION RESULT:\n{execution_result[:4000]}\n\nReview this subtask. Respond ONLY with JSON:\n{{"approved": true/false, "confidence": 0.0-1.0, "issues": [...], "feedback": "...", "notes": "..."}}'
        try:
            raw = self._call_llm(system=SUBTASK_REVIEW_SYSTEM_PROMPT, user_content=user_content, model=model, max_tokens=1024, temperature=0.2)
            return self._parse_json_safe(raw, default=default)
        except Exception as e:
            log.error(f'DeepThink subtask review error: {e}')
            return default

    def think(self, user_message: str, extra_context: str='', conversation: list=None, on_token: Any=None) -> str:
        """DeepThink direkt aufrufen für komplexe Fragen."""
        if not self.is_enabled():
            return 'DeepThink nicht konfiguriert.'
        model = self.settings.get('deepthink_model', '')
        system = self.DEEP_THINK_PROMPT.format(extra_context=extra_context)
        messages = []
        if conversation:
            for msg in conversation[-5:]:
                role = msg.get('role', '')
                content = msg.get('content', '')
                if role in ('user', 'assistant') and content:
                    messages.append({'role': role, 'content': content})
        if not messages or messages[-1].get('content') != user_message:
            messages.append({'role': 'user', 'content': user_message})
        try:
            return self._call_llm(system=system, messages=messages, model=model, max_tokens=self.settings.get('max_tokens', 4096), temperature=0.7, on_token=on_token)
        except Exception as e:
            log.error(f'DeepThink think error: {e}')
            return f'Fehler im DeepThink-Modul: {e}'
        
    def validate_action(self, tool: str, params: dict, user_query: str) -> bool:
        """
        Nutzt MiniMax M2.5, um zu entscheiden, ob ein Tool-Call sicher ist.
        """
        audit_prompt = f"""
        ### SICHERHEITS-AUDIT ###
        Der User möchte: "{user_query}"
        
        Der KI-Agent plant folgende Aktion:
        Tool: {tool}
        Parameter: {json.dumps(params, indent=2)}
        
        ENTSCHEIDUNGSRICHTLINIEN:
        1. Ist die Aktion gefährlich (z.B. Systemdateien lesen)?
        2. Führt die Aktion zu Datenverlust (z.B. Code in write_file wirkt unvollständig)?
        3. Passt die Aktion logisch zur User-Anfrage?

        Antworte NUR mit dem Wort 'YES' wenn die Aktion sicher ist, oder mit 'NO', wenn sie blockiert werden muss.
        """
        
        try:
            # Wir rufen think() nur mit dem Prompt auf, wie in deiner Klasse definiert
            response = self.think(audit_prompt) 
            
            # Logge die Entscheidung für das Terminal
            decision = "APPROVED ✅" if "YES" in response.upper() else "REJECTED ❌"
            log.info(f"Audit-Ergebnis für {tool}: {decision}")
            
            return "YES" in response.upper()
        except Exception as e:
            log.error(f"Fehler im DeepThink-Audit: {e}")
            return True # Fallback: Im Zweifel erlauben

    def _call_llm(self, system: str, model: str, max_tokens: int=1024, temperature: float=0.7, user_content: str='', messages: list=None, on_token: Any=None) -> str:
        """
        Interner LLM-Aufruf — provider-agnostisch.
        Entweder user_content (single turn) oder messages (multi turn) übergeben.
        """
        if messages is None:
            messages = [{'role': 'user', 'content': user_content}]
        if self.provider == 'anthropic':
            return self._call_anthropic(system, messages, model, max_tokens, temperature, on_token)
        else:
            return self._call_openai(system, messages, model, max_tokens, temperature, on_token)

    def _call_anthropic(self, system: Any, messages: Any, model: Any, max_tokens: Any, temperature: Any, on_token: Any=None) -> str:
        if on_token:
            full_text = ''
            with self.client.messages.stream(model=model, max_tokens=max_tokens, temperature=temperature, system=system, messages=messages) as stream:
                for text in stream.text_stream:
                    full_text += text
                    on_token(text)
            return full_text
        else:
            resp = self.client.messages.create(model=model, max_tokens=max_tokens, temperature=temperature, system=system, messages=messages)
            return resp.content[0].text

    def _call_openai(self, system: Any, messages: Any, model: Any, max_tokens: Any, temperature: Any, on_token: Any=None) -> str:
        oai_messages = [{'role': 'system', 'content': system}] + messages
        if on_token:
            full_text = ''
            stream = self.client.chat.completions.create(model=model, max_tokens=max_tokens, temperature=temperature, messages=oai_messages, stream=True)
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_text += token
                    on_token(token)
            return full_text
        else:
            resp = self.client.chat.completions.create(model=model, max_tokens=max_tokens, temperature=temperature, messages=oai_messages)
            return resp.choices[0].message.content

    def _parse_json_safe(self, raw: str, default: Any=None) -> Any:
        """Robustes JSON-Parsing mit Cleanup. Gibt default zurück bei Fehler."""
        if not raw:
            log.warning('Empty response for JSON parsing')
            return default
        cleaned = re.sub('<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
        cleaned = cleaned.removeprefix('```json').removeprefix('```').removesuffix('```').strip()
        json_match = re.search('\\{.*\\}', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)
        if cleaned and (not cleaned.endswith('}')):
            cleaned = cleaned.rstrip(',') + '\n}'
        if not cleaned:
            log.warning('Empty response after cleanup')
            return default
        try:
            result = json.loads(cleaned)
            return result
        except json.JSONDecodeError as e:
            log.warning(f'JSON parse failed ({e}). Raw: {cleaned[:300]}')
            return default
