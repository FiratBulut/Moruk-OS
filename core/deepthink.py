"""
Moruk AI OS - DeepThink v2 (Reviewer & Advisor)
Rolle: Review, Decompose, Deep Analysis.
NICHT mehr: Tool-Blocking, Action-Validation (das macht brain.py lokal).

Änderungen v2:
- validate_action() entfernt (war zu aggressiv, blockierte alles)
- review_tool_call() → nur noch Advisory, blockiert NICHT mehr
- Neue Methode: advisory_check() → gibt Warnung zurück, kein Block
- think() gibt bei Fehler "" zurück → Caller entscheidet, nicht DeepThink
- should_review() Schwelle angepasst (nur bei depth >= 4 UND langen Antworten)
"""

from typing import Any
import json
import re
from pathlib import Path
from core.logger import get_logger

log = get_logger("deepthink")
DATA_DIR = Path(__file__).parent.parent / "data"

REVIEW_SYSTEM_PROMPT = """You are a strict AI supervisor. Your job is to review responses from a smaller AI model.

Evaluate the response for:
1. Correctness — Is the answer factually accurate and logically sound?
2. Completeness — Does it fully address the user's request?
3. Safety — Does it contain risky actions (e.g. file deletions, destructive commands) without justification?
4. Clarity — Is it clear and not confusing or misleading?

Respond ONLY with a JSON object in this exact format (no markdown, no extra text):
{
  "verdict": "approve" | "revise" | "reject",
  "confidence": 0.0-1.0,
  "issues": ["issue1", "issue2"],
  "suggestion": "What the model should do differently (only if verdict is revise or reject)"
}

Verdicts:
- approve: Response is good. No changes needed.
- revise: Response has fixable issues. Provide a suggestion.
- reject: Response is wrong, dangerous, or completely misses the point. You will answer directly instead.

Be strict but fair. Only revise/reject when clearly necessary."""

DECOMPOSE_SYSTEM_PROMPT = """You are a senior software architect. Your job is to break down project requests into concrete, ordered subtasks.

Rules:
- Each subtask must be a single, atomic unit of work.
- Order by dependency (what must be built first)."""


class DeepThink:
    def __init__(self):
        self.client = None
        self.settings = {}
        self.enabled = False
        self._provider_type = "openai_compatible"

    def configure(self, settings: dict):
        self.settings = settings
        self._init_client()

    def _init_client(self):
        provider = self.settings.get("deepthink_provider", "")
        api_key = self.settings.get("deepthink_api_key", "")
        base_url = self.settings.get("deepthink_base_url", "")

        if not provider or (provider != "ollama" and not api_key):
            self.client = None
            self.enabled = False
            return

        try:
            if provider == "anthropic":
                from anthropic import Anthropic
                self.client = Anthropic(api_key=api_key)
                self._provider_type = "anthropic"
                self.enabled = True
            elif provider == "ollama":
                from openai import OpenAI
                url = base_url or "http://localhost:11434/v1"
                self.client = OpenAI(base_url=url, api_key="ollama")
                self._provider_type = "openai_compatible"
                self.enabled = True
            else:
                from openai import OpenAI
                self.client = (
                    OpenAI(base_url=base_url, api_key=api_key)
                    if base_url
                    else OpenAI(api_key=api_key)
                )
                self._provider_type = "openai_compatible"
                self.enabled = True

        except Exception as e:
            log.error(f"DeepThink client init failed: {e}")
            self.client = None
            self.enabled = False

    def is_enabled(self) -> bool:
        return self.enabled and self.client is not None

    # ── 1. Trigger Detection ───────────────────────────────────

    def should_think_deep(self, user_message: str) -> bool:
        """Prüft, ob der User explizit den DeepThink-Modus triggern will."""
        if not self.is_enabled():
            return False

        trigger_words = [
            "denk nach", "deepthink", "analysiere tief",
            "überleg genau", "schreibe ein konzept",
        ]
        msg_lower = user_message.lower().strip()
        return any(msg_lower.startswith(w) for w in trigger_words)

    # ── 2. Advisory Check (ersetzt review_tool_call) ──────────

    def advisory_check(self, tool_name: str, params: dict) -> dict:
        """
        Lightweight lokaler Check — gibt Advisory zurück, BLOCKIERT NICHT.
        brain.py entscheidet selbst ob es die Warnung ernst nimmt.
        Returns: {"warning": str or "", "severity": "none"|"low"|"high"}
        """
        if tool_name == "terminal":
            cmd = params.get("command", "").strip().lower()
            # Absolute No-Gos — das sind die einzigen harten Blocks
            critical = ["rm -rf /", "mkfs", "dd if=", "> /dev/sda", "chmod -R 777 /"]
            if any(f in cmd for f in critical):
                return {
                    "warning": f"Kritisch destruktiver Befehl: {cmd[:80]}",
                    "severity": "high",
                }

            # Warnungen (kein Block, nur Info)
            risky = ["rm ", "rm\t", "rmdir", "mv /", "chmod", "chown", "kill ", "pkill"]
            if any(cmd.startswith(r) or f" {r}" in cmd for r in risky):
                return {
                    "warning": f"Potentiell riskanter Befehl: {cmd[:80]}",
                    "severity": "low",
                }

        return {"warning": "", "severity": "none"}

    # ── 3. Review (Haupt-Rolle von DeepThink) ─────────────────

    def should_review(self, user_message: str, full_response: str, depth: int) -> bool:
        """Heuristik: Braucht diese Antwort einen Supervisor-Review?
        Nur bei hohem Depth UND substanziellen Antworten."""
        if not self.is_enabled():
            return False

        # Nur bei depth >= 4 (Projekte, autonome Tasks)
        if depth < 4:
            return False

        # Bei Code oder sehr langen Antworten
        if "```" in full_response and len(full_response) > 1500:
            return True
        if len(full_response) > 3000:
            return True

        return False

    def review(self, user_message: str, response_to_review: str) -> dict:
        """Supervisor-Review einer generierten Antwort."""
        if not self.is_enabled():
            return {"verdict": "approve"}

        prompt = f"USER REQUEST:\n{user_message}\n\nAI RESPONSE TO REVIEW:\n{response_to_review}"
        raw = self.think(prompt, extra_context=REVIEW_SYSTEM_PROMPT, max_tokens=500)

        if not raw:
            # DeepThink antwortet nicht → approve (fail-open)
            return {"verdict": "approve", "confidence": 0.5}

        parsed = self._parse_json_safe(raw, default={"verdict": "approve"})
        return parsed

    def review_multi_agent(self, task_description: str, agent_results: str) -> dict:
        """Review für Multi-Agent Ergebnisse. Gibt strukturiertes Feedback."""
        if not self.is_enabled():
            return {"approved": True, "feedback": "", "summary": "DeepThink offline"}

        prompt = (
            f"Original task: {task_description}\n\n"
            f"Agent results:{agent_results}\n\n"
            "Review all results. Are they correct and complete? "
            'Respond ONLY with JSON: {"approved": true/false, "feedback": "...", "summary": "..."}'
        )

        raw = self.think(prompt, max_tokens=800)
        if not raw:
            return {"approved": True, "feedback": "", "summary": "Review unavailable"}

        parsed = self._parse_json_safe(raw, default={"approved": True})
        return parsed

    # ── 4. Decompose ──────────────────────────────────────────

    def decompose_task(self, task_description: str) -> list:
        """Zerlegt einen großen Task in Subtasks."""
        if not self.is_enabled():
            return []

        raw = self.think(
            task_description, extra_context=DECOMPOSE_SYSTEM_PROMPT, max_tokens=2000
        )
        parsed = self._parse_json_safe(raw, default=[])
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict) and "tasks" in parsed:
            return parsed["tasks"]
        return []

    # ── 5. Core Think (API Call) ──────────────────────────────

    def think(
        self,
        user_message: str,
        extra_context: str = "",
        conversation: list = None,
        on_token=None,
        max_tokens: int = None,
    ) -> str:
        """Führt den API-Call an das DeepThink Modell aus.
        Returns: Response text oder "" bei Fehler (fail-open)."""
        if not self.is_enabled():
            return ""

        model = self.settings.get("deepthink_model", "")
        max_t = (
            max_tokens
            if max_tokens
            else self.settings.get("deepthink_max_tokens", 8192)
        )
        temperature = self.settings.get("deepthink_temperature", 0.6)

        messages = []
        if conversation:
            messages.extend(conversation)

        sys_prompt = "You are the DeepThink analysis engine of Moruk OS. Think step-by-step and provide comprehensive, highly accurate answers."
        if extra_context:
            sys_prompt += f"\n\nContext:\n{extra_context}"

        call_messages = [{"role": "system", "content": sys_prompt}] + messages
        if not conversation or call_messages[-1]["role"] != "user":
            call_messages.append({"role": "user", "content": user_message})

        try:
            if self._provider_type == "anthropic":
                filtered = [m for m in call_messages if m["role"] != "system"]
                if on_token:
                    full_text = ""
                    with self.client.messages.stream(
                        model=model,
                        max_tokens=max_t,
                        temperature=temperature,
                        system=sys_prompt,
                        messages=filtered,
                    ) as stream:
                        for text in stream.text_stream:
                            full_text += text
                            on_token(text)
                    return full_text
                else:
                    resp = self.client.messages.create(
                        model=model,
                        max_tokens=max_t,
                        temperature=temperature,
                        system=sys_prompt,
                        messages=filtered,
                    )
                    return resp.content[0].text
            else:
                if on_token:
                    full_text = ""
                    stream = self.client.chat.completions.create(
                        model=model,
                        max_tokens=max_t,
                        temperature=temperature,
                        messages=call_messages,
                        stream=True,
                    )
                    for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            token = chunk.choices[0].delta.content
                            full_text += token
                            on_token(token)
                    return full_text
                else:
                    resp = self.client.chat.completions.create(
                        model=model,
                        max_tokens=max_t,
                        temperature=temperature,
                        messages=call_messages,
                    )
                    return resp.choices[0].message.content
        except Exception as e:
            log.error(f"DeepThink API Call failed: {e}")
            return ""

    # ── Hilfsfunktionen ─────────────────────────────────────────

    def _parse_json_safe(self, raw: str, default: Any = None) -> Any:
        """Robustes JSON-Parsing mit Cleanup. Gibt default zurück bei Fehler."""
        if not raw:
            log.warning("Empty response for JSON parsing")
            return default

        # <think> Blöcke (wie bei DeepSeek) entfernen
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        # Markdown Code-Blöcke entfernen
        cleaned = (
            cleaned.removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )

        # Versuchen, das erste JSON-Objekt/Array im Text zu finden
        json_match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)

        # Unvollständige JSONs notdürftig flicken
        if cleaned and cleaned.startswith("{") and not cleaned.endswith("}"):
            cleaned = cleaned.rstrip(",") + "\n}"

        if not cleaned:
            log.warning("Empty response after cleanup")
            return default

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            log.warning(f"JSON parse failed ({e}). Raw: {cleaned[:150]}...")
            return default
