"""
Moruk AI OS - Context Router
Intelligentes Token-Management: Klassifiziert Input → bestimmt Kontext-Tiefe.
Spart 60-90% Tokens bei einfachen Nachrichten.
"""

import re
import json
import os
from datetime import datetime
from pathlib import Path
from core.logger import get_logger

log = get_logger("router")

DATA_DIR = Path(__file__).parent.parent / "data"

# Gemeinsamer Pfad für beide Klassen
SUMMARY_PATH = DATA_DIR / "conversation_summary.json"

# ═══════════════════════════════════════════════
# Intent Classification (OHNE LLM - regelbasiert!)
# ═══════════════════════════════════════════════

SMALLTALK_PATTERNS = [
    r'^(hi|hey|hallo|moin|servus|yo|sup|na)\s*[!?.]*$',
    r'^(guten\s*(morgen|abend|tag)|good\s*(morning|evening))\s*[!?.]*$',
    r'^wie\s*geht\s*(es\s*)?(dir|s)\s*[?!.]*$',
    r'^(how\s*are\s*you|what\'?s?\s*up)\s*[?!.]*$',
    r'^(danke|thanks|thx|ok|okay|cool|nice|gut|super|alles\s*klar)\s*[!?.]*$',
    r'^(bye|tschüss|ciao|see\s*ya)\s*[!?.]*$',
    r'^(ja|nein|yes|no|yep|nope|klar|sicher)\s*[!?.]*$',
]

ACTION_KEYWORDS = [
    'erstell', 'create', 'bau', 'build', 'mach', 'make', 'schreib', 'write',
    'install', 'deploy', 'starte', 'start', 'run', 'ausführ', 'execute',
    'lösch', 'delete', 'entfern', 'remove', 'fix', 'reparier', 'debug',
    'ändere', 'change', 'update', 'modif', 'edit', 'programmier', 'code',
    'implementier', 'develop', 'konfigur', 'config', 'setup',
    'suche', 'search', 'find', 'finde', 'lookup', 'research', 'analysier',
    'zeig', 'show', 'liste', 'list', 'vergleich', 'compare', 'prüf', 'check',
    'lade', 'download', 'öffne', 'open', 'lese', 'read', 'scrap',
]

DEV_KEYWORDS = [
    'python', 'javascript', 'html', 'css', 'react', 'api', 'server',
    'function', 'class', 'import', 'bug', 'error', 'traceback', 'exception',
    'git', 'commit', 'docker', 'database', 'sql', 'script', 'code',
    'file', 'datei', 'ordner', 'folder', 'path', 'terminal', 'bash',
    'pip', 'npm', 'package', 'module', 'library',
]

RECALL_KEYWORDS = [
    'erinnerst', 'remember', 'weisst', 'know', 'was war', 'what was',
    'letzte', 'last', 'vorher', 'before', 'gestern', 'yesterday',
    'mein name', 'my name', 'über mich', 'about me',
]

SELF_KEYWORDS = [
    'self_edit', 'architecture', 'dein code', 'your code', 'verbessere dich',
    'improve yourself', 'änder dich', 'modify yourself', 'self-improvement',
]


class ContextRouter:
    """Klassifiziert User-Input und routet zum minimalen Kontext."""

    DEPTH_MINIMAL = 1
    DEPTH_QUESTION = 2
    DEPTH_TASK = 3
    DEPTH_DEV = 4
    DEPTH_AUTONOMOUS = 5

    def __init__(self):
        self.message_count = 0

    def classify(self, message: str, has_attachments: bool = False) -> dict:
        """
        Klassifiziert eine Nachricht.
        Returns: {
            "intent": "smalltalk|question|task|dev|recall|self_edit",
            "depth": 1-5,
            "context_flags": {"memory": bool, "tasks": bool, "reflections": bool, "state": bool},
            "max_tokens": int,
            "temperature": float
        }
        """
        msg_lower = message.lower().strip()
        self.message_count += 1

        if has_attachments:
            return self._make_result("task", self.DEPTH_TASK,
                                     memory=True, tasks=False, reflections=False, state=True)

        if self._is_smalltalk(msg_lower):
            log.info(f"Classified as SMALLTALK: '{msg_lower[:40]}'")
            return self._make_result("smalltalk", self.DEPTH_MINIMAL,
                                     memory=False, tasks=False, reflections=False, state=False,
                                     max_tokens=150, temperature=0.5)

        if self._has_keywords(msg_lower, SELF_KEYWORDS):
            log.info(f"Classified as SELF_EDIT: '{msg_lower[:40]}'")
            return self._make_result("self_edit", self.DEPTH_DEV,
                                     memory=True, tasks=True, reflections=True, state=True)

        if self._has_keywords(msg_lower, RECALL_KEYWORDS):
            log.info(f"Classified as RECALL: '{msg_lower[:40]}'")
            return self._make_result("recall", self.DEPTH_QUESTION,
                                     memory=True, tasks=False, reflections=False, state=True,
                                     max_tokens=500)

        if self._has_keywords(msg_lower, DEV_KEYWORDS) and self._has_keywords(msg_lower, ACTION_KEYWORDS):
            log.info(f"Classified as DEV: '{msg_lower[:40]}'")
            return self._make_result("dev", self.DEPTH_DEV,
                                     memory=True, tasks=True, reflections=True, state=True)

        if self._has_keywords(msg_lower, ACTION_KEYWORDS):
            log.info(f"Classified as TASK: '{msg_lower[:40]}'")
            return self._make_result("task", self.DEPTH_TASK,
                                     memory=True, tasks=True, reflections=False, state=True)

        if self._has_keywords(msg_lower, DEV_KEYWORDS):
            log.info(f"Classified as DEV-QUESTION: '{msg_lower[:40]}'")
            return self._make_result("question", self.DEPTH_QUESTION,
                                     memory=True, tasks=False, reflections=False, state=False,
                                     max_tokens=1000)

        if msg_lower.endswith('?') or msg_lower.startswith(('was ', 'wie ', 'wo ', 'wer ',
            'warum ', 'wann ', 'what ', 'how ', 'where ', 'who ', 'why ', 'when ',
            'kannst ', 'can ', 'ist ', 'is ', 'hat ', 'has ')):
            log.info(f"Classified as QUESTION: '{msg_lower[:40]}'")
            return self._make_result("question", self.DEPTH_QUESTION,
                                     memory=True, tasks=False, reflections=False, state=False,
                                     max_tokens=1000)

        if len(message) > 100:
            log.info(f"Classified as TASK (long message): '{msg_lower[:40]}'")
            return self._make_result("task", self.DEPTH_TASK,
                                     memory=True, tasks=True, reflections=False, state=True)

        log.info(f"Classified as QUESTION (default): '{msg_lower[:40]}'")
        return self._make_result("question", self.DEPTH_QUESTION,
                                 memory=True, tasks=False, reflections=False, state=False,
                                 max_tokens=800)

    def build_context(self, classification: dict, state=None, memory=None,
                      tasks=None, reflector=None, query: str = "") -> str:
        """Baut minimalen Kontext basierend auf Classification."""
        flags = classification["context_flags"]
        parts = []

        if flags.get("state") and state:
            parts.append(state.get_context_summary())

        if flags.get("memory") and memory:
            ctx = memory.get_memory_context(query=query, max_entries=5)
            if ctx and ctx != "No stored memories yet.":
                parts.append(ctx)

        if flags.get("tasks") and tasks:
            ctx = tasks.get_task_context()
            if ctx and ctx != "No active tasks.":
                parts.append(ctx)

        if flags.get("reflections") and reflector:
            ctx = reflector.get_reflection_context()
            if ctx:
                parts.append(ctx)

        context = "\n".join(parts)
        actual = len(context.split())
        log.info(f"Context: ~{actual} words sent ({classification['intent']}, depth={classification['depth']})")
        return context

    # ── Helpers ───────────────────────────────────────────────

    def _is_smalltalk(self, msg: str) -> bool:
        if len(msg) > 60:
            return False
        for pattern in SMALLTALK_PATTERNS:
            if re.match(pattern, msg, re.IGNORECASE):
                return True
        return False

    def _has_keywords(self, msg: str, keywords: list) -> bool:
        return any(kw in msg for kw in keywords)

    def _make_result(self, intent: str, depth: int, memory: bool = False,
                     tasks: bool = False, reflections: bool = False,
                     state: bool = False, max_tokens: int = 4096,
                     temperature: float = 0.7) -> dict:
        return {
            "intent": intent,
            "depth": depth,
            "context_flags": {
                "memory": memory,
                "tasks": tasks,
                "reflections": reflections,
                "state": state
            },
            "max_tokens": max_tokens,
            "temperature": temperature
        }


# ═══════════════════════════════════════════════
# History Compressor
# ═══════════════════════════════════════════════

class HistoryCompressor:
    """Komprimiert Chat-History um Tokens zu sparen."""

    COMPRESS_AFTER = 10
    KEEP_RECENT = 4

    def __init__(self):
        self.summary_path = SUMMARY_PATH  # Gemeinsames Constant
        self.summaries = self._load_summaries()

    def _load_summaries(self) -> list:
        if self.summary_path.exists():
            try:
                with open(self.summary_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def _save_summaries(self):
        """Speichert Summaries atomar."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = self.summary_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.summaries[-20:], f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.summary_path)
        except Exception as e:
            log.error(f"Fehler beim Speichern der Summaries: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def should_compress(self, history: list) -> bool:
        return len(history) > self.COMPRESS_AFTER

    def compress(self, history: list) -> list:
        """
        Komprimiert History: Alte Messages → Summary, behalte letzte N.
        Returns: Neue, kürzere History.
        """
        if len(history) <= self.KEEP_RECENT:
            return history

        old_messages = history[:-self.KEEP_RECENT]
        recent = history[-self.KEEP_RECENT:]

        topics = set()
        tools_used = set()
        actions = []

        for msg in old_messages:
            content = str(msg.get("content", ""))[:200]
            role = msg.get("role", "")

            if role == "user":
                words = content.lower().split()
                for w in words:
                    if len(w) > 4 and w not in ('nicht', 'diese', 'einen', 'meine', 'werden',
                                                  'about', 'there', 'would', 'could', 'should'):
                        topics.add(w)

            if "<tool_call>" in content:
                # re ist oben importiert — kein inline Import nötig
                tools = re.findall(r'"tool":\s*"(\w+)"', content)
                tools_used.update(tools)

            if role == "assistant" and len(content) > 50:
                first_line = content.split('\n')[0][:100]
                actions.append(first_line)

        summary = {
            "timestamp": datetime.now().isoformat(),
            "message_count": len(old_messages),
            "topics": list(topics)[:20],
            "tools_used": list(tools_used),
            "key_actions": actions[-5:],
        }

        self.summaries.append(summary)
        self._save_summaries()

        summary_text = self._format_summary(summary)
        compressed = [
            {"role": "user", "content": f"[Previous conversation summary: {summary_text}]"},
            {"role": "assistant", "content": "Understood, I have context from our previous conversation."}
        ]
        compressed.extend(recent)

        old_tokens = sum(len(str(m.get("content", "")).split()) for m in history)
        new_tokens = sum(len(str(m.get("content", "")).split()) for m in compressed)
        log.info(f"History compressed: {len(history)} → {len(compressed)} messages, "
                 f"~{old_tokens} → ~{new_tokens} words")

        return compressed

    def _format_summary(self, summary: dict) -> str:
        parts = []
        if summary.get("topics"):
            parts.append(f"Topics: {', '.join(summary['topics'][:10])}")
        if summary.get("tools_used"):
            parts.append(f"Tools used: {', '.join(summary['tools_used'])}")
        if summary.get("key_actions"):
            parts.append(f"Recent actions: {'; '.join(summary['key_actions'][:3])}")
        return " | ".join(parts) if parts else "General conversation"

    def get_context_summary(self) -> str:
        if not self.summaries:
            return ""
        last = self.summaries[-1]
        return f"Previous context: {self._format_summary(last)}"
