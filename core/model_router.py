"""
Moruk AI OS — Model Router
Entscheidet automatisch welches Modell für welche Anfrage genutzt wird.

Tier-System:
  fast  → Small Model (immer verfügbar, günstig, schnell)
           Für: Smalltalk, einfache Fragen, Recall, kurze Tasks
  deep  → DeepThink (stark, teurer, langsamer)
           Für: Code, Planung, Architektur, Self-Edit, kritische Entscheidungen

Entscheidungslogik:
  1. Explizites Override (force_deepthink, 🧠-Button) → immer deep
  2. Intent/Depth aus ContextRouter → Basis-Entscheidung
  3. Message-Analyse (Komplexitätsindikatoren) → kann hochstufen
  4. DeepThink nicht verfügbar → immer fast (kein Fehler)
"""

import re
from core.logger import get_logger

log = get_logger("model_router")

# ── Komplexitäts-Keywords ─────────────────────────────────────

# Diese Patterns → immer DeepThink wenn verfügbar
DEEP_PATTERNS = [
    # Architektur & Planung
    r"\b(architektur|architecture|design|entw(urf|erfen))\b",
    r"\b(plan(e|ung|nen)?|konzept|roadmap|strateg)\b",
    r"\b(refactor|rewrite|restructur|umschreib)\b",
    # Code-Komplexität
    r"\b(algorithm|optimier|performance|memory.leak)\b",
    r"\b(class\s+\w+|inheritance|abstract|interface)\b",
    r"\b(async|concurrent|thread|parallel|race.condition)\b",
    r"\b(security|vuln|exploit|inject|auth)\b",
    # System-Eingriffe
    r"\b(self.edit|self_edit|modif(y|iere).*(brain|core|plugin))\b",
    r"\b(deploy|release|publish|veröffentlich)\b",
    r"\b(debug.*complex|trace.*error|root.cause)\b",
    # Analyse & Review
    r"\b(review|analys[ei]|evaluat|bewert|prüfe.*(code|architektur))\b",
    r"\b(vergleich|compare|vs\.?|trade.off|pros.*cons)\b",
    # Kreativ-komplex
    r"\b(erkläre.*(warum|wie|was).*genau|explain.*in.detail)\b",
    r"\b(schritt.für.schritt|step.by.step)\b",
]

# Diese Patterns → fast ist ausreichend
FAST_PATTERNS = [
    r"^(hey|hi|hallo|hej|hello|moin)\b",
    r"^(danke|thanks|thx|ok|okay|gut|super|cool|nice)\b",
    r"^(ja|nein|yes|no|jep|nope|klar)\b",
    r"\b(wie spät|uhrzeit|datum|wetter|was kostet)\b",
    r"\b(zeig mir|liste|list|zeige|show)\b(?!.*(architektur|komplex|design))",
    r"\b(erkläre kurz|brief|kurz|tldr|tl;dr)\b",
]

# Intent → Tier Mapping (aus ContextRouter)
INTENT_TIER = {
    "smalltalk": "fast",
    "question": "fast",  # Einfache Fragen → fast; Komplexitätsprüfung kann hochstufen
    "recall": "fast",
    "task": "fast",  # Standard-Tasks; Komplexitätsprüfung kann hochstufen
    "dev": "deep",  # Dev-Tasks immer deep
    "self_edit": "deep",  # Self-Edit immer deep
}

# Depth → Tier Mapping (Fallback wenn intent unbekannt)
DEPTH_TIER = {
    1: "fast",
    2: "fast",
    3: "fast",
    4: "deep",
    5: "deep",
}


class ModelRouter:
    """
    Entscheidet welches Modell-Tier für eine Anfrage optimal ist.
    Wird zwischen ContextRouter und Brain geschaltet.
    """

    def __init__(self, deepthink_available: bool = False):
        self.deepthink_available = deepthink_available
        self._deep_patterns = [re.compile(p, re.IGNORECASE) for p in DEEP_PATTERNS]
        self._fast_patterns = [re.compile(p, re.IGNORECASE) for p in FAST_PATTERNS]
        self._decisions = []  # Letzte N Entscheidungen für Stats

    def update_deepthink_status(self, available: bool):
        """Wird von brain.py aufgerufen wenn DeepThink (de)aktiviert wird."""
        self.deepthink_available = available

    # ── Haupt-Entscheidung ─────────────────────────────────────

    def decide(
        self, message: str, classification: dict, force_deep: bool = False
    ) -> dict:
        """
        Entscheidet Modell-Tier für eine Anfrage.

        Returns:
            {
                "tier":   "fast" | "deep",
                "reason": str,              # Für Logging/UI
                "use_deepthink": bool,      # True wenn deep UND deepthink verfügbar
                "confidence": float         # 0.0-1.0
            }
        """
        # 1. Explizites Override → immer deep
        if force_deep:
            return self._result("deep", "force_deepthink by user", 1.0)

        intent = classification.get("intent", "question")
        depth = classification.get("depth", 3)

        # 2. Explizit-Fast: eindeutige Smalltalk-Patterns
        if self._matches_fast(message):
            return self._result("fast", f"fast pattern match (intent={intent})", 0.9)

        # 3. Intent/Depth Basis-Tier
        base_tier = INTENT_TIER.get(intent, DEPTH_TIER.get(depth, "fast"))

        # 4. Komplexitätsanalyse — kann fast → deep hochstufen
        if base_tier == "fast":
            complexity = self._analyze_complexity(message)
            if complexity["is_complex"]:
                return self._result(
                    "deep",
                    f"complexity escalation: {complexity['reason']} (was intent={intent})",
                    complexity["confidence"],
                )

        # 5. Basis-Tier zurückgeben
        reason = f"intent={intent}, depth={depth}"
        return self._result(base_tier, reason, 0.85)

    # ── Pattern-Matching ──────────────────────────────────────

    def _matches_fast(self, message: str) -> bool:
        msg = message.strip()
        return len(msg) < 30 and any(p.search(msg) for p in self._fast_patterns)

    def _analyze_complexity(self, message: str) -> dict:
        """Analysiert ob eine Nachricht DeepThink-würdig ist."""
        msg = message.strip()

        # Explizite Deep-Pattern
        for pattern in self._deep_patterns:
            m = pattern.search(msg)
            if m:
                return {
                    "is_complex": True,
                    "reason": f"keyword '{m.group(0)}'",
                    "confidence": 0.9,
                }

        # Längen-Heuristik: sehr lange Messages sind oft komplex
        if len(msg) > 400:
            return {
                "is_complex": True,
                "reason": f"long message ({len(msg)} chars)",
                "confidence": 0.7,
            }

        # Code-Blöcke
        if "```" in msg or msg.count("`") >= 3:
            return {
                "is_complex": True,
                "reason": "code block in message",
                "confidence": 0.85,
            }

        # Viele Fragen auf einmal
        question_marks = msg.count("?")
        if question_marks >= 3:
            return {
                "is_complex": True,
                "reason": f"multi-question ({question_marks}x?)",
                "confidence": 0.75,
            }

        return {"is_complex": False, "reason": "", "confidence": 0.0}

    # ── Helpers ───────────────────────────────────────────────

    def _result(self, tier: str, reason: str, confidence: float) -> dict:
        use_deepthink = (tier == "deep") and self.deepthink_available
        result = {
            "tier": tier,
            "reason": reason,
            "use_deepthink": use_deepthink,
            "confidence": confidence,
        }
        # Letzte 20 Entscheidungen für Stats speichern
        self._decisions.append(result)
        self._decisions = self._decisions[-20:]
        log.debug(f"ModelRouter → {tier.upper()} ({reason}) deepthink={use_deepthink}")
        return result

    def get_stats(self) -> dict:
        """Stats für Sidebar."""
        if not self._decisions:
            return {"total": 0, "fast": 0, "deep": 0, "deep_pct": 0}
        total = len(self._decisions)
        deep = sum(1 for d in self._decisions if d["tier"] == "deep")
        fast = total - deep
        return {
            "total": total,
            "fast": fast,
            "deep": deep,
            "deep_pct": round(deep / total * 100, 1),
        }
