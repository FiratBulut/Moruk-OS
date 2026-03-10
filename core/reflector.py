"""
Moruk AI OS - Reflector v3 (Meta-Cognition Engine)
1. Structured JSON Reflections
2. Confidence-based Strategy Rules
3. Periodic Improvement Engine (log analysis)
4. Reflection Budget (lightweight, no extra LLM calls)
"""

import json
import os
from datetime import datetime
from pathlib import Path
from collections import Counter
from core.logger import get_logger

log = get_logger("reflector")
DATA_DIR = Path(__file__).parent.parent / "data"

# Stats werden alle N Aktionen auf Disk geschrieben (statt bei jeder Aktion)
STATS_SAVE_INTERVAL = 10


class Reflector:
    """Meta-Cognition Engine für Moruk OS."""

    def __init__(self, memory=None):
        self.memory = memory
        self.log_path = DATA_DIR / "reflection_log.json"
        self.stats_path = DATA_DIR / "reflection_stats.json"
        self.strategy_path = DATA_DIR / "strategy_rules.json"
        self.log = self._load_json(self.log_path, [])
        self.stats = self._load_stats()
        self.strategy_rules = self._load_json(self.strategy_path, [])
        self._improvement_counter = 0
        self._stats_dirty_count = 0  # Zählt ungespeicherte Stats-Updates

    # ── Persistence ───────────────────────────────────────────

    def _load_json(self, path: Path, default):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return default

    def _load_stats(self) -> dict:
        return self._load_json(
            self.stats_path,
            {
                "total_actions": 0,
                "successful_actions": 0,
                "failed_actions": 0,
                "tool_usage": {},
                "error_patterns": [],
                "lessons_learned": 0,
                "streak": {"current": 0, "best": 0},
            },
        )

    def _atomic_write(self, path: Path, data, trim_fn=None):
        """Schreibt JSON atomar via Temp-Datei. Optional: trim_fn(data) vor dem Schreiben."""
        path.parent.mkdir(
            parents=True, exist_ok=True
        )  # Sicherstellen dass data/ existiert
        tmp_path = path.with_suffix(".tmp")
        try:
            payload = trim_fn(data) if trim_fn else data
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception as e:
            log.error(f"Fehler beim atomaren Schreiben von {path.name}: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def _save_log(self):
        self._atomic_write(self.log_path, self.log, trim_fn=lambda d: d[-300:])

    def _save_stats(self, force: bool = False):
        """Speichert Stats nur alle STATS_SAVE_INTERVAL Aktionen oder wenn force=True."""
        self._stats_dirty_count += 1
        if force or self._stats_dirty_count >= STATS_SAVE_INTERVAL:
            self._atomic_write(self.stats_path, self.stats)
            self._stats_dirty_count = 0

    def _save_strategy(self):
        self._atomic_write(
            self.strategy_path, self.strategy_rules, trim_fn=lambda d: d[-50:]
        )

    def flush(self):
        """Erzwingt sofortiges Speichern aller dirty Stats (z.B. beim Shutdown)."""
        if self._stats_dirty_count > 0:
            self._atomic_write(self.stats_path, self.stats)
            self._stats_dirty_count = 0

    # ══════════════════════════════════════════════════════════
    # 1. STRUCTURED JSON REFLECTIONS
    # ══════════════════════════════════════════════════════════

    def reflect(self, action: str, result: str, success: bool, lesson: str = ""):
        """Structured reflection mit JSON-Schema."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action[:200],
            "result": result[:500],
            "success": success,
            "lesson": lesson,
            "tool": (
                action.split(":")[0]
                if ":" in action
                else action.split()[0] if action else "unknown"
            ),
            "error_type": self._classify_error(result) if not success else None,
            "duration_context": "fast",  # Placeholder, kein Timing nötig
        }

        self.log.append(entry)
        self.log = self.log[-300:]
        self._save_log()

        # Stats aktualisieren (lazy save)
        self._update_stats(entry)

        # Lessons ins Langzeit-Gedächtnis
        if lesson and self.memory:
            self.stats["lessons_learned"] += 1
            self.memory.remember_long(
                content=f"Lesson: {lesson} (from: {action[:80]})",
                category="reflection",
                tags=["lesson", "self-improvement"],
            )

        # Strategy Rule generieren bei Fehler
        if not success:
            self._maybe_generate_rule(entry)

        # Periodische Improvement-Analyse
        self._improvement_counter += 1
        if self._improvement_counter >= 20:
            self._improvement_counter = 0
            self.run_improvement_analysis()

    def auto_reflect_tool(self, tool_name: str, params: dict, result: dict):
        """Auto-Reflexion nach Tool-Ausführung (lightweight)."""
        success = result.get("success", False)
        result_text = str(result.get("result", ""))[:300]
        action = f"{tool_name}: {json.dumps(params, ensure_ascii=False)[:100]}"

        lesson = ""
        if not success:
            error_type = self._classify_error(result_text)
            lesson = self._auto_lesson(tool_name, error_type, result_text)

        self.reflect(action, result_text, success, lesson)

    def _classify_error(self, text: str) -> str:
        """Klassifiziert Fehler in Kategorien."""
        text_lower = text.lower()
        if "permission denied" in text_lower:
            return "permission"
        elif "no such file" in text_lower or "not found" in text_lower:
            return "file_not_found"
        elif "timeout" in text_lower:
            return "timeout"
        elif "importerror" in text_lower or "modulenotfounderror" in text_lower:
            return "missing_module"
        elif "syntax" in text_lower:
            return "syntax_error"
        elif "connection" in text_lower or "refused" in text_lower:
            return "connection"
        elif "memory" in text_lower or "oom" in text_lower:
            return "memory"
        else:
            return "unknown"

    def _auto_lesson(self, tool: str, error_type: str, result: str) -> str:
        """Generiert Lesson basierend auf Error-Type (ohne LLM)."""
        lessons = {
            "permission": f"Permission denied bei {tool}. Sudo oder Pfad-Rechte prüfen.",
            "file_not_found": f"Datei nicht gefunden bei {tool}. Existenz vorher mit read_file prüfen.",
            "timeout": f"Timeout bei {tool}. Befehl optimieren oder aufteilen.",
            "missing_module": "Modul fehlt. Erst installieren: pip install <module>",
            "syntax_error": "Syntax-Fehler im Code. Vor dem Schreiben nochmal prüfen.",
            "connection": "Verbindungsfehler. Netzwerk/URL prüfen.",
            "memory": "Speicher-Problem. Aufgabe in kleinere Teile aufteilen.",
        }
        return lessons.get(error_type, f"Fehler bei {tool}: {result[:80]}")

    # ══════════════════════════════════════════════════════════
    # 2. CONFIDENCE-BASED STRATEGY RULES
    # ══════════════════════════════════════════════════════════

    def _maybe_generate_rule(self, entry: dict):
        """Generiert eine Strategy-Rule wenn ein Fehler-Pattern erkannt wird."""
        error_type = entry.get("error_type", "unknown")
        tool = entry.get("tool", "unknown")

        recent_errors = [
            e
            for e in self.log[-50:]
            if not e.get("success")
            and e.get("error_type") == error_type
            and e.get("tool") == tool
        ]

        if len(recent_errors) < 2:
            return  # Erst ab 2x Pattern

        rule_key = f"{tool}:{error_type}"
        existing = None
        for rule in self.strategy_rules:
            if rule.get("key") == rule_key:
                existing = rule
                break

        if existing:
            existing["occurrences"] += 1
            existing["confidence"] = min(1.0, existing["confidence"] + 0.1)
            existing["updated"] = datetime.now().isoformat()
            log.info(
                f"Strategy rule updated: {rule_key} → confidence={existing['confidence']:.2f}"
            )
        else:
            rule_text = self._generate_rule_text(tool, error_type)
            new_rule = {
                "key": rule_key,
                "rule": rule_text,
                "confidence": 0.5,
                "occurrences": len(recent_errors),
                "created": datetime.now().isoformat(),
                "updated": datetime.now().isoformat(),
            }
            self.strategy_rules.append(new_rule)
            log.info(f"New strategy rule: {rule_key} → '{rule_text}'")

        self._save_strategy()

    def _generate_rule_text(self, tool: str, error_type: str) -> str:
        """Generiert Regeltext basierend auf Tool + Error-Type (ohne LLM)."""
        rules = {
            (
                "terminal",
                "permission",
            ): "Before running privileged commands, check if sudo is needed",
            (
                "terminal",
                "timeout",
            ): "For long-running commands, add timeout or run in background",
            (
                "terminal",
                "file_not_found",
            ): "Always verify file paths exist before using them",
            (
                "write_file",
                "permission",
            ): "Check write permissions before creating files",
            (
                "read_file",
                "file_not_found",
            ): "Use terminal 'ls' to verify path before reading",
            (
                "terminal",
                "missing_module",
            ): "Install required modules before importing them",
            (
                "self_edit",
                "syntax_error",
            ): "Review code carefully before self-editing, use smaller changes",
        }
        return rules.get(
            (tool, error_type),
            f"When using {tool}: handle {error_type} errors. Check prerequisites first.",
        )

    def get_strategy_rules(self, min_confidence: float = 0.3) -> list:
        """Gibt aktive Strategy-Rules über Confidence-Schwelle."""
        return [
            r for r in self.strategy_rules if r.get("confidence", 0) >= min_confidence
        ]

    def decay_confidence(self):
        """Reduziert Confidence von alten Regeln (Time-Decay)."""
        now = datetime.now()
        for rule in self.strategy_rules:
            try:
                updated = datetime.fromisoformat(rule.get("updated", now.isoformat()))
                age_days = (now - updated).days
                if age_days > 7:
                    rule["confidence"] = max(0.1, rule["confidence"] - 0.05)
            except (ValueError, TypeError):
                pass
        self._save_strategy()

    # ══════════════════════════════════════════════════════════
    # 3. IMPROVEMENT ENGINE (Periodische Log-Analyse)
    # ══════════════════════════════════════════════════════════

    def run_improvement_analysis(self) -> dict:
        """
        Analysiert die letzten Logs und generiert Insights.
        Wird automatisch alle ~20 Aktionen aufgerufen.
        Kein LLM nötig – rein regelbasiert.
        """
        analysis = {
            "timestamp": datetime.now().isoformat(),
            "insights": [],
            "recommendations": [],
        }

        recent = self.log[-50:]
        if len(recent) < 5:
            return analysis

        # ── Fehlerrate-Analyse ──
        total = len(recent)
        failures = [e for e in recent if not e.get("success")]
        failure_rate = len(failures) / total

        if failure_rate > 0.4:
            analysis["insights"].append(
                {
                    "type": "high_failure_rate",
                    "value": f"{failure_rate:.0%}",
                    "detail": "Fehlerrate über 40% in den letzten Aktionen",
                }
            )
            analysis["recommendations"].append(
                "Komplexe Aufgaben in kleinere Schritte aufteilen"
            )

        # ── Wiederholte Fehler ──
        error_types = Counter(
            e.get("error_type") for e in failures if e.get("error_type")
        )
        for error_type, count in error_types.most_common(3):
            if count >= 3:
                analysis["insights"].append(
                    {
                        "type": "repeated_error",
                        "value": error_type,
                        "count": count,
                        "detail": f"'{error_type}' tritt häufig auf ({count}x)",
                    }
                )

        # ── Tool-Effizienz ──
        tool_stats = {}
        for entry in recent:
            tool = entry.get("tool", "unknown")
            if tool not in tool_stats:
                tool_stats[tool] = {"total": 0, "success": 0}
            tool_stats[tool]["total"] += 1
            if entry.get("success"):
                tool_stats[tool]["success"] += 1

        for tool, stats in tool_stats.items():
            if stats["total"] >= 3:
                rate = stats["success"] / stats["total"]
                if rate < 0.5:
                    analysis["insights"].append(
                        {
                            "type": "low_tool_efficiency",
                            "tool": tool,
                            "success_rate": f"{rate:.0%}",
                            "detail": f"Tool '{tool}' hat nur {rate:.0%} Erfolgsrate",
                        }
                    )
                    analysis["recommendations"].append(
                        f"Alternative Strategie für '{tool}' finden oder Vorbedingungen prüfen"
                    )

        # ── Streak-Analyse ──
        current_streak = self.stats.get("streak", {}).get("current", 0)
        best_streak = self.stats.get("streak", {}).get("best", 0)
        if current_streak >= 10:
            analysis["insights"].append(
                {
                    "type": "good_streak",
                    "value": current_streak,
                    "detail": f"Aktuelle Erfolgsserie: {current_streak} (Best: {best_streak})",
                }
            )

        # ── Confidence Decay ──
        self.decay_confidence()

        # Speichern + flush stats
        self.flush()

        if analysis["insights"]:
            log.info(
                f"Improvement analysis: {len(analysis['insights'])} insights, "
                f"{len(analysis['recommendations'])} recommendations"
            )

            if self.memory and len(analysis["insights"]) >= 2:
                summary = "; ".join([i["detail"] for i in analysis["insights"][:3]])
                self.memory.remember_long(
                    content=f"Self-analysis: {summary}",
                    category="reflection",
                    tags=["meta-cognition", "improvement"],
                )

        return analysis

    # ══════════════════════════════════════════════════════════
    # STATS & CONTEXT
    # ══════════════════════════════════════════════════════════

    def _update_stats(self, entry: dict):
        self.stats["total_actions"] += 1
        if entry["success"]:
            self.stats["successful_actions"] += 1
            self.stats["streak"]["current"] += 1
            if self.stats["streak"]["current"] > self.stats["streak"]["best"]:
                self.stats["streak"]["best"] = self.stats["streak"]["current"]
        else:
            self.stats["failed_actions"] += 1
            self.stats["streak"]["current"] = 0

        tool = entry.get("tool", "unknown")
        self.stats["tool_usage"][tool] = self.stats["tool_usage"].get(tool, 0) + 1

        if not entry["success"] and entry.get("result"):
            self.stats["error_patterns"].append(
                {
                    "error": entry["result"][:200],
                    "error_type": entry.get("error_type", "unknown"),
                    "tool": tool,
                    "timestamp": entry["timestamp"],
                }
            )
            self.stats["error_patterns"] = self.stats["error_patterns"][-50:]

        # Lazy save: nur alle STATS_SAVE_INTERVAL Aktionen schreiben
        self._save_stats()

    def get_success_rate(self) -> float:
        total = self.stats.get("total_actions", 0)
        if total == 0:
            return 0.0
        return (self.stats.get("successful_actions", 0) / total) * 100

    def get_most_used_tools(self, n: int = 5) -> list:
        usage = self.stats.get("tool_usage", {})
        return sorted(usage.items(), key=lambda x: x[1], reverse=True)[:n]

    def get_common_errors(self, n: int = 5) -> list:
        errors = self.stats.get("error_patterns", [])
        if not errors:
            return []
        error_texts = [e.get("error", "")[:80] for e in errors]
        return Counter(error_texts).most_common(n)

    def get_recent_reflections(self, n: int = 5) -> list:
        return self.log[-n:]

    def get_reflection_context(self) -> str:
        """Kontext für System Prompt – enthält Strategy Rules."""
        parts = []

        total = self.stats.get("total_actions", 0)
        if total > 0:
            rate = self.get_success_rate()
            streak = self.stats.get("streak", {}).get("current", 0)
            parts.append(
                f"Performance: {total} actions, {rate:.0f}% success, streak: {streak}"
            )

        active_rules = self.get_strategy_rules(min_confidence=0.5)
        if active_rules:
            parts.append("Learned Rules:")
            for rule in active_rules[:5]:
                parts.append(f"  • [{rule['confidence']:.0%}] {rule['rule']}")

        recent = self.get_recent_reflections(2)
        if recent:
            parts.append("Recent:")
            for r in recent:
                status = "✓" if r["success"] else "✗"
                parts.append(f"  {status} {r['action'][:60]}")

        common_errors = self.get_common_errors(2)
        if common_errors:
            parts.append("Watch out:")
            for error, count in common_errors:
                parts.append(f"  ⚠ ({count}x) {error[:60]}")

        return "\n".join(parts) if parts else ""

    def reflect_on_project(
        self,
        project_title: str,
        subtask_results: list,
        final_approved: bool,
        final_verdict: str = "",
    ):
        """Reflection nach einem abgeschlossenen Projekt — lernt aus Erfolgen und Fehlern."""
        total = len(subtask_results)
        approved = sum(1 for r in subtask_results if r.get("approved", False))
        failed = total - approved

        # Jede Subtask-Review als Reflection eintragen
        for i, review in enumerate(subtask_results):
            success = review.get("approved", False)
            issues = ", ".join(review.get("issues", [])) or "none"
            feedback = review.get("feedback", "")
            lesson = feedback if not success and feedback else ""
            self.reflect(
                action=f"project_subtask:{project_title}[{i+1}/{total}]",
                result=f"approved={success}, issues={issues}",
                success=success,
                lesson=lesson,
            )

        # Gesamt-Projekt Reflection
        summary = (
            f"Project '{project_title}': {approved}/{total} subtasks approved. "
            f"Final: {'✅' if final_approved else '❌'} {final_verdict[:100]}"
        )
        lesson = ""
        if not final_approved:
            lesson = (
                f"Project failed: {final_verdict[:150]}. Review subtask decomposition."
            )
        elif failed > 0:
            lesson = (
                f"Project completed with {failed} failed subtasks. Check retry logic."
            )

        self.reflect(
            action=f"project_complete:{project_title}",
            result=summary,
            success=final_approved,
            lesson=lesson,
        )

        # Ins Langzeit-Gedächtnis
        if self.memory:
            self.memory.remember_long(
                content=summary,
                category="project_reflection",
                tags=["project", "completed" if final_approved else "failed"],
            )

        log.info(f"Project reflection saved: {summary}")
        return {"total": total, "approved": approved, "failed": failed}

    def get_full_stats(self) -> dict:
        return {
            **self.stats,
            "success_rate": self.get_success_rate(),
            "most_used_tools": self.get_most_used_tools(),
            "common_errors": self.get_common_errors(),
            "strategy_rules_count": len(self.strategy_rules),
            "active_rules": len(self.get_strategy_rules(min_confidence=0.5)),
            # Fix: strategy_rules selbst auch mitliefern für GoalEngine etc.
            "strategy_rules": self.get_strategy_rules(min_confidence=0.3),
        }
