"""
Moruk AI OS - User Profile Engine
Lernt den User über Sessions hinweg: Präferenzen, Stil, häufige Aufgaben, Sprache.

Speichert strukturiert in data/user_profile.json.
Wird bei jedem think() in den System-Prompt injiziert.
Wird nach jeder Session automatisch aktualisiert.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter
from core.logger import get_logger

log = get_logger("user_profile")
DATA_DIR = Path(__file__).parent.parent / "data"


class UserProfileEngine:
    """
    Lernt den User kennen über:
    - Sprache & Kommunikationsstil
    - Häufige Aufgabentypen
    - Bevorzugte Tools/Workflows
    - Tageszeit-Muster
    - Explizite Präferenzen ("ich mag...", "mach immer...")
    - Interessen & Domänen
    """

    VERSION = "1.0"

    # Aufgaben-Kategorien mit Keywords
    TASK_CATEGORIES = {
        "coding":       ["code", "python", "plugin", "script", "function", "bug", "fix",
                         "write", "implement", "class", "def ", "import", "error", "syntax"],
        "research":     ["search", "find", "what is", "explain", "how does", "research",
                         "suche", "erkläre", "was ist", "wie funktioniert"],
        "system":       ["system", "health", "check", "monitor", "cpu", "ram", "disk",
                         "process", "install", "update", "repair"],
        "creative":     ["create", "generate", "image", "video", "design", "write story",
                         "erstelle", "generiere", "schreib"],
        "organization": ["task", "goal", "plan", "organize", "schedule", "todo",
                         "aufgabe", "plane", "organisiere"],
        "analysis":     ["analyze", "review", "check", "compare", "evaluate",
                         "analysiere", "prüfe", "vergleiche"],
        "automation":   ["automate", "loop", "run automatically", "schedule",
                         "automatisiere", "lauf automatisch"],
    }

    # Explizite Präferenz-Patterns
    PREFERENCE_PATTERNS = [
        r"(?:ich mag|i like|i prefer|ich bevorzuge|mach immer|always)\s+(.+?)(?:\.|$)",
        r"(?:ich will|i want|i need|ich brauche)\s+(?:immer|always)\s+(.+?)(?:\.|$)",
        r"(?:bitte|please)\s+(?:immer|always)\s+(.+?)(?:\.|$)",
        r"(?:mein stil|my style|ich schreibe|i write)\s+(.+?)(?:\.|$)",
    ]

    def __init__(self):
        self.profile_path = DATA_DIR / "user_profile.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.profile = self._load()

    # ── Load / Save ───────────────────────────────────────────

    def _load(self) -> dict:
        if self.profile_path.exists():
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Migration: ältere Versionen
                    return self._migrate(data)
            except Exception as e:
                log.warning(f"Profile load failed: {e} — using default")
        return self._default()

    def _default(self) -> dict:
        return {
            "version": self.VERSION,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "sessions_analyzed": 0,
            "total_messages": 0,

            # Sprache & Stil
            "language": {
                "primary": "unknown",       # "de", "en", "mixed"
                "formality": "neutral",     # "formal", "casual", "neutral"
                "response_length": "medium" # "short", "medium", "detailed"
            },

            # Aufgaben-Verteilung
            "task_distribution": {},        # category → count

            # Häufige Themen/Keywords
            "frequent_topics": {},          # word → count

            # Tageszeit-Muster
            "activity_hours": {},           # "HH" → count

            # Explizite Präferenzen (vom User direkt geäußert)
            "explicit_preferences": [],     # ["immer auf Deutsch antworten", ...]

            # Interessen-Domänen (hochrangig)
            "domains": [],                  # ["AI/ML", "System Admin", ...]

            # Workflow-Präferenzen
            "workflow": {
                "prefers_explanations": True,
                "prefers_code_examples": False,
                "prefers_step_by_step": False,
                "asks_followups": False,
            },

            # Letzte Sessions (für Trending)
            "recent_sessions": [],          # [{date, message_count, main_tasks}, ...]
        }

    def _migrate(self, data: dict) -> dict:
        """Fügt fehlende Keys aus _default() hinzu (Rückwärtskompatibilität)."""
        default = self._default()
        for key, value in default.items():
            if key not in data:
                data[key] = value
            elif isinstance(value, dict) and isinstance(data[key], dict):
                for subkey, subval in value.items():
                    if subkey not in data[key]:
                        data[key][subkey] = subval
        return data

    def save(self):
        self.profile["updated_at"] = datetime.now().isoformat()
        tmp = self.profile_path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.profile, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.profile_path)
        except Exception as e:
            log.error(f"Profile save failed: {e}")

    # ── Analysis ──────────────────────────────────────────────

    def analyze_session(self, messages: list):
        """
        Analysiert eine Session und updatet das Profil.
        messages: Liste von {role, content} dicts
        """
        if not messages:
            return

        user_msgs = [m for m in messages if m.get("role") == "user"
                     and not str(m.get("content", "")).startswith("<tool_results>")]

        if not user_msgs:
            return

        self.profile["sessions_analyzed"] += 1
        self.profile["total_messages"] += len(user_msgs)

        # Alle User-Texte zusammen
        all_text = " ".join(str(m.get("content", "")) for m in user_msgs).lower()

        # 1. Sprache erkennen
        self._detect_language(all_text)

        # 2. Aufgaben-Kategorien zählen
        session_tasks = []
        for msg in user_msgs:
            text = str(msg.get("content", "")).lower()
            for category, keywords in self.TASK_CATEGORIES.items():
                if any(kw in text for kw in keywords):
                    dist = self.profile["task_distribution"]
                    dist[category] = dist.get(category, 0) + 1
                    session_tasks.append(category)

        # 3. Häufige Keywords extrahieren
        self._extract_topics(all_text)

        # 4. Tageszeit tracken
        hour = str(datetime.now().hour).zfill(2)
        hours = self.profile["activity_hours"]
        hours[hour] = hours.get(hour, 0) + 1

        # 5. Explizite Präferenzen suchen
        for msg in user_msgs:
            self._detect_preferences(str(msg.get("content", "")))

        # 6. Workflow-Stil lernen
        self._analyze_workflow_style(user_msgs)

        # 7. Domänen ableiten
        self._update_domains()

        # 8. Response Length Präferenz aus Assistant-Antworten
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
        if assistant_msgs:
            avg_len = sum(len(str(m.get("content", ""))) for m in assistant_msgs) / len(assistant_msgs)
            if avg_len < 300:
                self.profile["language"]["response_length"] = "short"
            elif avg_len < 1200:
                self.profile["language"]["response_length"] = "medium"
            else:
                self.profile["language"]["response_length"] = "detailed"

        # 9. Session-Summary speichern
        main_tasks = Counter(session_tasks).most_common(2)
        self.profile["recent_sessions"].append({
            "date": datetime.now().date().isoformat(),
            "message_count": len(user_msgs),
            "main_tasks": [t[0] for t in main_tasks],
        })
        # Max 20 Sessions behalten
        self.profile["recent_sessions"] = self.profile["recent_sessions"][-20:]

        self.save()
        log.info(f"User profile updated — session #{self.profile['sessions_analyzed']}")

    def _detect_language(self, text: str):
        de_words = ["ich", "du", "er", "sie", "wir", "nicht", "und", "oder",
                    "aber", "dass", "mit", "von", "ist", "sind", "war", "bitte",
                    "danke", "mach", "zeig", "schreib", "erkläre", "kannst"]
        en_words = ["i", "you", "he", "she", "we", "not", "and", "or",
                    "but", "that", "with", "from", "is", "are", "was",
                    "please", "thanks", "make", "show", "write", "explain", "can"]

        words = text.split()
        de_count = sum(1 for w in words if w in de_words)
        en_count = sum(1 for w in words if w in en_words)

        if de_count > en_count * 1.5:
            self.profile["language"]["primary"] = "de"
        elif en_count > de_count * 1.5:
            self.profile["language"]["primary"] = "en"
        else:
            self.profile["language"]["primary"] = "mixed"

        # Formalität
        casual_de = ["hey", "hallo", "voll", "krass", "ok", "jo", "ne", "naja", "mal"]
        casual_en = ["hey", "yeah", "cool", "ok", "nope", "yep", "gonna", "wanna"]
        if any(w in text for w in casual_de + casual_en):
            self.profile["language"]["formality"] = "casual"

    def _extract_topics(self, text: str):
        # Stopwords rausfiltern
        stopwords = {
            "ich", "du", "er", "sie", "es", "wir", "ihr", "den", "dem", "des",
            "ein", "eine", "der", "die", "das", "und", "oder", "aber", "nicht",
            "mit", "von", "aus", "bei", "nach", "vor", "über", "unter",
            "i", "you", "he", "she", "it", "we", "the", "a", "an", "and",
            "or", "but", "not", "with", "from", "at", "by", "for", "in",
            "is", "are", "was", "be", "to", "of", "that", "this", "have",
            "bitte", "please", "kannst", "kann", "soll", "will", "mach", "make"
        }
        words = re.findall(r'\b[a-zA-ZäöüÄÖÜß]{4,}\b', text.lower())
        topics = self.profile["frequent_topics"]
        for word in words:
            if word not in stopwords:
                topics[word] = topics.get(word, 0) + 1

        # Top 100 behalten
        if len(topics) > 100:
            sorted_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)
            self.profile["frequent_topics"] = dict(sorted_topics[:100])

    def _detect_preferences(self, text: str):
        for pattern in self.PREFERENCE_PATTERNS:
            matches = re.findall(pattern, text.lower())
            for match in matches:
                pref = match.strip()[:100]
                if pref and pref not in self.profile["explicit_preferences"]:
                    self.profile["explicit_preferences"].append(pref)
                    log.info(f"New explicit preference detected: {pref}")

        # Max 20 explizite Präferenzen
        self.profile["explicit_preferences"] = self.profile["explicit_preferences"][-20:]

    def _analyze_workflow_style(self, user_msgs: list):
        all_text = " ".join(str(m.get("content", "")) for m in user_msgs).lower()

        # Fragt er nach Erklärungen?
        if any(w in all_text for w in ["erkläre", "explain", "warum", "why", "wie", "how"]):
            self.profile["workflow"]["prefers_explanations"] = True

        # Fragt er nach Code-Beispielen?
        if any(w in all_text for w in ["beispiel", "example", "zeig mir", "show me", "code"]):
            self.profile["workflow"]["prefers_code_examples"] = True

        # Schritt-für-Schritt?
        if any(w in all_text for w in ["schritt", "step by step", "nacheinander", "zuerst dann"]):
            self.profile["workflow"]["prefers_step_by_step"] = True

    def _update_domains(self):
        """Leitet Interessen-Domänen aus Task-Verteilung und Topics ab."""
        dist = self.profile["task_distribution"]
        topics = self.profile["frequent_topics"]
        domains = set()

        if dist.get("coding", 0) > 3:
            domains.add("Software Development")
        if dist.get("system", 0) > 3:
            domains.add("System Administration")
        if dist.get("research", 0) > 3:
            domains.add("Research & Analysis")
        if dist.get("creative", 0) > 2:
            domains.add("Creative Work")
        if dist.get("automation", 0) > 2:
            domains.add("Automation")

        # Topics-basiert
        ai_words = {"ai", "model", "llm", "neural", "machine", "learning", "plugin", "agent"}
        if sum(topics.get(w, 0) for w in ai_words) > 5:
            domains.add("AI/ML")

        self.profile["domains"] = list(domains)

    # ── Context für System Prompt ──────────────────────────────

    def get_context_for_prompt(self) -> str:
        """
        Gibt personalisierten Kontext für den System-Prompt zurück.
        Wird in brain.py injiziert.
        """
        p = self.profile
        sessions = p.get("sessions_analyzed", 0)

        if sessions < 2:
            return ""  # Zu wenig Daten

        parts = ["--- USER PROFILE ---"]

        # Sprache
        lang = p.get("language", {})
        primary = lang.get("primary", "unknown")
        if primary == "de":
            parts.append("Language: Deutsch — antworte auf Deutsch")
        elif primary == "en":
            parts.append("Language: English — respond in English")
        elif primary == "mixed":
            parts.append("Language: Mixed DE/EN — match the user's language")

        formality = lang.get("formality", "neutral")
        if formality == "casual":
            parts.append("Style: Casual tone preferred")

        resp_len = lang.get("response_length", "medium")
        if resp_len == "short":
            parts.append("Response length: Keep responses concise")
        elif resp_len == "detailed":
            parts.append("Response length: User appreciates detailed explanations")

        # Häufigste Aufgaben
        dist = p.get("task_distribution", {})
        if dist:
            top_tasks = sorted(dist.items(), key=lambda x: x[1], reverse=True)[:3]
            parts.append(f"Main tasks: {', '.join(t[0] for t in top_tasks)}")

        # Domänen
        domains = p.get("domains", [])
        if domains:
            parts.append(f"Domains: {', '.join(domains)}")

        # Workflow
        wf = p.get("workflow", {})
        wf_hints = []
        if wf.get("prefers_code_examples"):
            wf_hints.append("include code examples")
        if wf.get("prefers_step_by_step"):
            wf_hints.append("use step-by-step structure")
        if wf_hints:
            parts.append(f"Workflow: {', '.join(wf_hints)}")

        # Explizite Präferenzen
        prefs = p.get("explicit_preferences", [])
        if prefs:
            parts.append(f"Explicit preferences: {'; '.join(prefs[:5])}")

        # Aktivste Zeiten (für proaktive Goals)
        hours = p.get("activity_hours", {})
        if hours:
            peak_hour = max(hours, key=hours.get)
            parts.append(f"Usually active around: {peak_hour}:00")

        parts.append(f"(Profile based on {sessions} sessions)")

        return "\n".join(parts)

    def get_summary(self) -> str:
        """Human-readable Summary für Sidebar/Stats."""
        p = self.profile
        sessions = p.get("sessions_analyzed", 0)
        if sessions == 0:
            return "No profile data yet — keep chatting!"

        lang = p.get("language", {}).get("primary", "?")
        domains = ", ".join(p.get("domains", [])) or "unknown"
        top_task = ""
        dist = p.get("task_distribution", {})
        if dist:
            top = max(dist, key=dist.get)
            top_task = f"  Main task: {top} ({dist[top]}x)\n"

        prefs = p.get("explicit_preferences", [])
        pref_str = ""
        if prefs:
            pref_str = "  Preferences:\n" + "\n".join(f"    - {p}" for p in prefs[:3])

        return (
            f"User Profile ({sessions} sessions analyzed)\n"
            f"  Language: {lang}\n"
            f"  Domains: {domains}\n"
            f"{top_task}"
            f"  Topics: {', '.join(list(p.get('frequent_topics', {}).keys())[:5])}\n"
            f"{pref_str}"
        )
