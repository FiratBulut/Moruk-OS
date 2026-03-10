"""
Moruk AI OS - Self-Model Module
Der Agent kennt sich selbst: Stärken, Schwächen, Confidence pro Skill.
Passt sein Verhalten automatisch an.

Daten: data/self_profile.json
Update: Nach jeder Tool-Ausführung, Task-Completion, alle 15 Aktionen.
"""

import json
import math
from datetime import datetime
from pathlib import Path
from core.logger import get_logger

log = get_logger("self_model")
DATA_DIR = Path(__file__).parent.parent / "data"


class SelfModel:
    """Moruk's Selbstbild: Capabilities, Stärken, Schwächen, Confidence."""

    STRENGTH_THRESHOLD = 0.85  # success_rate > 85% = Stärke
    WEAKNESS_THRESHOLD = 0.50  # success_rate < 50% = Schwäche
    MIN_RUNS_FOR_EVAL = 5  # Mindestens 5 Runs für Bewertung
    CONFIDENCE_DECAY = 0.98  # Pro Stunde
    UPDATE_INTERVAL = 15  # Alle 15 Aktionen Update

    def __init__(self):
        self.profile_path = DATA_DIR / "self_profile.json"
        self.profile = self._load_profile()
        self._action_counter = 0

    def _load_profile(self) -> dict:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if self.profile_path.exists():
            try:
                with open(self.profile_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return self._default_profile()

    def _default_profile(self) -> dict:
        return {
            "capabilities": {},
            "strengths": [],
            "weaknesses": [],
            "tool_stats": {},
            "error_patterns": {},
            "decision_profile": {
                "risk_tolerance": 0.5,
                "planning_depth": 0.5,
                "exploration_bias": 0.3,
            },
            "last_updated": datetime.now().isoformat(),
            "total_actions": 0,
        }

    def _save_profile(self):
        tmp_path = self.profile_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w") as f:
                json.dump(self.profile, f, indent=2, ensure_ascii=False)
            tmp_path.replace(self.profile_path)
        except Exception as e:
            log.error(f"Failed to save self-profile: {e}")
            if tmp_path.exists():
                tmp_path.unlink()

    # ══════════════════════════════════════════════
    # 1. CAPABILITY TRACKER
    # ══════════════════════════════════════════════

    def record_action(self, tool: str, success: bool, error_type: str = None):
        """Zeichnet eine Tool-Ausführung auf und aktualisiert das Profil."""
        # Tool Stats updaten
        if tool not in self.profile["tool_stats"]:
            self.profile["tool_stats"][tool] = {
                "runs": 0,
                "successes": 0,
                "failures": 0,
            }

        stats = self.profile["tool_stats"][tool]
        stats["runs"] += 1
        if success:
            stats["successes"] += 1
        else:
            stats["failures"] += 1

        # Error Pattern tracken
        if not success and error_type:
            if error_type not in self.profile["error_patterns"]:
                self.profile["error_patterns"][error_type] = 0
            self.profile["error_patterns"][error_type] += 1

        self.profile["total_actions"] = self.profile.get("total_actions", 0) + 1
        self._action_counter += 1

        # Capability Score berechnen
        self._update_capability(tool)

        # Periodisches Full-Update
        if self._action_counter >= self.UPDATE_INTERVAL:
            self._action_counter = 0
            self._full_update()

        self._save_profile()

    def _update_capability(self, tool: str):
        """Berechnet success_rate und confidence für ein Tool."""
        stats = self.profile["tool_stats"].get(tool, {})
        runs = stats.get("runs", 0)
        successes = stats.get("successes", 0)

        if runs == 0:
            return

        success_rate = successes / runs

        # Confidence = success_rate * log(runs + 1)
        # Normalisiert auf 0-1
        raw_confidence = success_rate * math.log(runs + 1)
        confidence = min(1.0, raw_confidence / math.log(100))  # Normalisierung

        self.profile["capabilities"][tool] = {
            "success_rate": round(success_rate, 3),
            "confidence": round(confidence, 3),
            "runs": runs,
        }

    # ══════════════════════════════════════════════
    # 2. STRENGTH / WEAKNESS DETECTION
    # ══════════════════════════════════════════════

    def _full_update(self):
        """Vollständiges Profil-Update: Stärken, Schwächen, Decision Profile."""
        strengths = []
        weaknesses = []

        for tool, cap in self.profile["capabilities"].items():
            runs = cap.get("runs", 0)
            rate = cap.get("success_rate", 0)

            if runs < self.MIN_RUNS_FOR_EVAL:
                continue

            if rate >= self.STRENGTH_THRESHOLD:
                strengths.append(tool)
            elif rate <= self.WEAKNESS_THRESHOLD:
                weaknesses.append(tool)

        # Auch Error Patterns als Schwächen
        for error_type, count in self.profile["error_patterns"].items():
            if count >= 5:
                weakness_name = f"handling_{error_type}"
                if weakness_name not in weaknesses:
                    weaknesses.append(weakness_name)

        self.profile["strengths"] = strengths
        self.profile["weaknesses"] = weaknesses

        # Decision Profile anpassen
        self._update_decision_profile()

        # Confidence Decay
        self._apply_decay()

        self.profile["last_updated"] = datetime.now().isoformat()
        log.info(
            f"Self-model updated: {len(strengths)} strengths, {len(weaknesses)} weaknesses"
        )

    def _update_decision_profile(self):
        """Passt risk_tolerance und planning_depth basierend auf Performance an."""
        caps = self.profile["capabilities"]
        if not caps:
            return

        # Durchschnittliche Success Rate
        rates = [c["success_rate"] for c in caps.values() if c.get("runs", 0) >= 3]
        if not rates:
            return

        avg_rate = sum(rates) / len(rates)
        dp = self.profile["decision_profile"]

        # Hohe Erfolgsrate → mehr Risikobereitschaft
        dp["risk_tolerance"] = round(min(0.8, max(0.2, avg_rate * 0.8)), 3)

        # Viele Schwächen → mehr Planung
        weakness_count = len(self.profile["weaknesses"])
        dp["planning_depth"] = round(min(0.9, 0.4 + weakness_count * 0.1), 3)

        # Wenig Erfahrung → mehr Exploration
        total = self.profile.get("total_actions", 0)
        dp["exploration_bias"] = round(max(0.1, 0.5 - total * 0.002), 3)

    def _apply_decay(self):
        """Confidence Decay: Alte Bewertungen verlieren an Gewicht."""
        for tool, cap in self.profile["capabilities"].items():
            cap["confidence"] = round(
                max(0.1, cap["confidence"] * self.CONFIDENCE_DECAY), 3
            )

    # ══════════════════════════════════════════════
    # 3. DECISION MODIFIER
    # ══════════════════════════════════════════════

    def get_advice(self, tool: str) -> dict:
        """
        Gibt Empfehlung VOR einer Tool-Ausführung.
        Returns: {"safe": bool, "advice": str, "confidence": float, "alternatives": []}
        """
        cap = self.profile["capabilities"].get(tool)
        is_weakness = tool in self.profile["weaknesses"]

        if not cap:
            return {
                "safe": True,
                "advice": f"No data for '{tool}' yet. Proceed carefully.",
                "confidence": 0.5,
                "alternatives": [],
            }

        confidence = cap["confidence"]
        rate = cap["success_rate"]

        advice = {
            "safe": True,
            "advice": "",
            "confidence": confidence,
            "alternatives": [],
        }

        if is_weakness:
            advice["safe"] = False
            advice["advice"] = (
                f"⚠ '{tool}' is a known weakness (success: {rate:.0%}). "
                f"Consider: verify inputs first, use smaller steps, or try alternatives."
            )
            # Alternativen vorschlagen
            alternatives = self._find_alternatives(tool)
            if alternatives:
                advice["alternatives"] = alternatives
        elif rate < 0.7:
            advice["advice"] = (
                f"'{tool}' has moderate reliability ({rate:.0%}). Extra caution recommended."
            )
        else:
            advice["advice"] = (
                f"'{tool}' is reliable ({rate:.0%}, confidence: {confidence:.0%})."
            )

        return advice

    def _find_alternatives(self, tool: str) -> list:
        """Schlägt alternative Tools vor basierend auf Stärken."""
        alt_map = {
            "web_request": ["terminal (curl)"],
            "write_file": ["terminal (echo > file)"],
            "self_edit": ["write_file + backup"],
            "terminal": ["write_file + python exec"],
        }
        return alt_map.get(tool, [])

    # ══════════════════════════════════════════════
    # 4. CONTEXT FOR SYSTEM PROMPT
    # ══════════════════════════════════════════════

    def get_self_awareness_context(self) -> str:
        """Injiziert Selbstbewusstsein in den System Prompt."""
        parts = []

        strengths = self.profile.get("strengths", [])
        weaknesses = self.profile.get("weaknesses", [])

        if strengths:
            parts.append(f"Your strengths: {', '.join(strengths)}")
        if weaknesses:
            parts.append(
                f"Your weaknesses: {', '.join(weaknesses)} — be extra careful here"
            )

        # Top capabilities
        caps = self.profile.get("capabilities", {})
        top = sorted(
            caps.items(), key=lambda x: x[1].get("confidence", 0), reverse=True
        )[:3]
        if top:
            parts.append(
                "Top skills: "
                + ", ".join(f"{t}({c['success_rate']:.0%})" for t, c in top)
            )

        dp = self.profile.get("decision_profile", {})
        if dp.get("risk_tolerance", 0.5) < 0.35:
            parts.append("Strategy: Be cautious, plan more, verify before executing.")
        elif dp.get("risk_tolerance", 0.5) > 0.65:
            parts.append("Strategy: You're performing well, act confidently.")

        return "\n".join(parts) if parts else ""

    def get_profile_summary(self) -> str:
        """Kurze Zusammenfassung für Stats-Anzeige."""
        total = self.profile.get("total_actions", 0)
        caps = self.profile.get("capabilities", {})
        strengths = self.profile.get("strengths", [])
        weaknesses = self.profile.get("weaknesses", [])
        dp = self.profile.get("decision_profile", {})

        lines = [
            f"Total Actions: {total}",
            f"Skills tracked: {len(caps)}",
            f"Strengths: {', '.join(strengths) if strengths else 'none yet'}",
            f"Weaknesses: {', '.join(weaknesses) if weaknesses else 'none yet'}",
            f"Risk tolerance: {dp.get('risk_tolerance', 0.5):.0%}",
            f"Planning depth: {dp.get('planning_depth', 0.5):.0%}",
        ]

        # Top/Bottom skills
        if caps:
            sorted_caps = sorted(
                caps.items(), key=lambda x: x[1].get("success_rate", 0)
            )
            if sorted_caps:
                worst = sorted_caps[0]
                best = sorted_caps[-1]
                lines.append(f"Best: {best[0]} ({best[1]['success_rate']:.0%})")
                lines.append(f"Worst: {worst[0]} ({worst[1]['success_rate']:.0%})")

        return "\n".join(lines)

    def get_full_profile(self) -> dict:
        return self.profile.copy()
