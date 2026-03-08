"""
Moruk AI OS - Monitor Engine
Beobachtet URLs, Suchbegriffe, GitHub Repos, Preise etc. periodisch.
Moruk analyzed die Ergebnisse und meldet Änderungen proaktiv.

Jeder Monitor hat:
  - type: search | url | github | price | custom
  - query / url: was beobachtet wird
  - interval_minutes: wie oft gecheckt wird
  - last_result: letztes Ergebnis (für Diff)
  - on_change: was Moruk tun soll wenn sich etwas ändert
"""

import json
import os
import time
import threading
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from core.logger import get_logger

log = get_logger("monitor_engine")

DATA_DIR  = Path(__file__).parent.parent / "data"
MONITORS_FILE = DATA_DIR / "monitors.json"

# Wird von autonomy_loop gesetzt
_brain = None
_notification_callback = None  # fn(title, message) für UI-Popup


class MonitorEngine:
    """Periodischer Web/Search Monitor mit Brain-Analyse."""

    DEFAULT_INTERVAL = 60  # Minuten

    # Monitor-Typen und ihre Such-Strategien
    TYPE_ICONS = {
        "search":  "🔍",
        "url":     "🌐",
        "github":  "🐙",
        "price":   "💰",
        "news":    "📰",
        "custom":  "📡",
    }

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.monitors = self._load()
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._brain = None
        self._notify = None

    # ── Persistence ───────────────────────────────────────────

    def _load(self) -> dict:
        if MONITORS_FILE.exists():
            try:
                with open(MONITORS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.warning(f"Monitors load failed: {e}")
        return {}

    def _save(self):
        tmp = MONITORS_FILE.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.monitors, f, indent=2, ensure_ascii=False)
            os.replace(tmp, MONITORS_FILE)
        except Exception as e:
            log.error(f"Monitors save failed: {e}")

    # ── CRUD ──────────────────────────────────────────────────

    def add_monitor(self, name: str, monitor_type: str, query: str,
                    interval_minutes: int = None, on_change: str = "notify") -> dict:
        """Fügt einen neuen Monitor hinzu."""
        if not name or not query:
            return {"success": False, "error": "name and query are required"}

        interval = interval_minutes or self.DEFAULT_INTERVAL
        monitor_id = name.lower().replace(" ", "_")[:40]

        with self._lock:
            self.monitors[monitor_id] = {
                "id":               monitor_id,
                "name":             name,
                "type":             monitor_type or "search",
                "query":            query,
                "interval_minutes": interval,
                "on_change":        on_change,  # "notify" | "act" | "log"
                "created_at":       datetime.now().isoformat(),
                "last_checked":     None,
                "next_check":       datetime.now().isoformat(),  # sofort beim ersten Mal
                "last_result_hash": None,
                "last_result":      None,
                "last_change":      None,
                "status":           "active",
                "check_count":      0,
                "change_count":     0,
            }
            self._save()

        log.info(f"Monitor added: {monitor_id} ({monitor_type}, every {interval}min)")
        return {"success": True, "id": monitor_id, "monitor": self.monitors[monitor_id]}

    def remove_monitor(self, monitor_id: str) -> dict:
        with self._lock:
            if monitor_id not in self.monitors:
                # Try by name
                for mid, m in self.monitors.items():
                    if m["name"].lower() == monitor_id.lower():
                        monitor_id = mid
                        break
                else:
                    return {"success": False, "error": f"Monitor '{monitor_id}' not found"}
            name = self.monitors[monitor_id]["name"]
            del self.monitors[monitor_id]
            self._save()
        return {"success": True, "removed": name}

    def list_monitors(self) -> list:
        with self._lock:
            return list(self.monitors.values())

    def get_monitor(self, monitor_id: str) -> dict | None:
        return self.monitors.get(monitor_id)

    def pause_monitor(self, monitor_id: str) -> dict:
        with self._lock:
            if monitor_id in self.monitors:
                self.monitors[monitor_id]["status"] = "paused"
                self._save()
                return {"success": True}
        return {"success": False, "error": "not found"}

    def resume_monitor(self, monitor_id: str) -> dict:
        with self._lock:
            if monitor_id in self.monitors:
                self.monitors[monitor_id]["status"] = "active"
                self.monitors[monitor_id]["next_check"] = datetime.now().isoformat()
                self._save()
                return {"success": True}
        return {"success": False, "error": "not found"}

    # ── Check Loop ────────────────────────────────────────────

    def start(self, brain=None, notify_fn=None):
        """Startet den Monitor-Loop in einem Background-Thread."""
        self._brain = brain
        self._notify = notify_fn
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info(f"MonitorEngine started ({len(self.monitors)} monitors)")

    def stop(self):
        self._running = False

    def _loop(self):
        """Main loop — checkt alle 60s ob ein Monitor fällig ist."""
        while self._running:
            try:
                self._tick()
            except Exception as e:
                log.error(f"Monitor loop error: {e}", exc_info=True)
            time.sleep(60)  # Jede Minute prüfen ob jemand fällig ist

    def _tick(self):
        """Prüft alle Monitors ob sie gecheckt werden müssen."""
        now = datetime.now()
        due = []

        with self._lock:
            for mid, monitor in self.monitors.items():
                if monitor.get("status") != "active":
                    continue
                next_check_str = monitor.get("next_check")
                if not next_check_str:
                    due.append(mid)
                    continue
                try:
                    next_check = datetime.fromisoformat(next_check_str)
                    if now >= next_check:
                        due.append(mid)
                except Exception:
                    due.append(mid)

        for mid in due:
            try:
                self._run_check(mid)
            except Exception as e:
                log.error(f"Check failed for {mid}: {e}")

    def _run_check(self, monitor_id: str):
        """Führt einen einzelnen Monitor-Check durch."""
        with self._lock:
            if monitor_id not in self.monitors:
                return
            monitor = dict(self.monitors[monitor_id])

        log.info(f"Running check: {monitor['name']} ({monitor['type']})")

        # Ergebnis holen
        result_text = self._fetch_result(monitor)
        if not result_text:
            return

        # Hash für Änderungs-Erkennung
        result_hash = hashlib.md5(result_text[:2000].encode()).hexdigest()
        has_changed = (monitor.get("last_result_hash") is not None and
                       result_hash != monitor.get("last_result_hash"))

        # Nächsten Check-Zeitpunkt berechnen
        interval = monitor.get("interval_minutes", self.DEFAULT_INTERVAL)
        next_check = (datetime.now() + timedelta(minutes=interval)).isoformat()

        with self._lock:
            if monitor_id not in self.monitors:
                return
            self.monitors[monitor_id].update({
                "last_checked":     datetime.now().isoformat(),
                "next_check":       next_check,
                "last_result_hash": result_hash,
                "last_result":      result_text[:1000],
                "check_count":      monitor.get("check_count", 0) + 1,
            })
            if has_changed:
                self.monitors[monitor_id]["last_change"] = datetime.now().isoformat()
                self.monitors[monitor_id]["change_count"] = monitor.get("change_count", 0) + 1
            self._save()

        # Bei Änderung: Brain analysieren lassen und notifizieren
        if has_changed:
            log.info(f"CHANGE DETECTED: {monitor['name']}")
            self._handle_change(monitor, result_text)

    def _fetch_result(self, monitor: dict) -> str | None:
        """Holt das aktuelle Ergebnis für einen Monitor."""
        mtype = monitor.get("type", "search")
        query = monitor.get("query", "")

        try:
            if mtype in ("search", "news"):
                return self._fetch_search(query)

            elif mtype == "url":
                return self._fetch_url(query)

            elif mtype == "github":
                return self._fetch_github(query)

            elif mtype == "price":
                return self._fetch_price(query)

            else:
                return self._fetch_search(query)

        except Exception as e:
            log.warning(f"Fetch failed for {monitor['name']}: {e}")
            return None

    def _fetch_search(self, query: str) -> str | None:
        try:
            from core.web_search import search_duckduckgo, format_search_results
            results = search_duckduckgo(query, num=5)
            return format_search_results(results)
        except Exception as e:
            log.warning(f"Search failed: {e}")
            return None

    def _fetch_url(self, url: str) -> str | None:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "MorukOS/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                content = r.read().decode("utf-8", errors="replace")
            # Nur Text, kein HTML
            import re
            text = re.sub(r'<[^>]+>', ' ', content)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:3000]
        except Exception as e:
            log.warning(f"URL fetch failed: {e}")
            return None

    def _fetch_github(self, repo: str) -> str | None:
        """Holt GitHub Releases/Issues für ein Repo."""
        try:
            import urllib.request, json as jsonlib
            # Format: owner/repo
            repo = repo.strip().strip("/")
            if "github.com/" in repo:
                repo = repo.split("github.com/")[-1].strip("/")
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            req = urllib.request.Request(url, headers={
                "User-Agent": "MorukOS/1.0",
                "Accept": "application/vnd.github.v3+json"
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                data = jsonlib.loads(r.read())
            tag  = data.get("tag_name", "?")
            name = data.get("name", "?")
            date = data.get("published_at", "?")[:10]
            body = data.get("body", "")[:500]
            return f"Latest release: {tag} — {name}\nPublished: {date}\n{body}"
        except Exception as e:
            log.warning(f"GitHub fetch failed: {e}")
            return self._fetch_search(f"github {repo} latest release")

    def _fetch_price(self, query: str) -> str | None:
        """Sucht nach Preisen (Krypto, Aktien, Produkte)."""
        return self._fetch_search(f"{query} current price today")

    # ── Change Handling ───────────────────────────────────────

    def _handle_change(self, monitor: dict, new_result: str):
        """Brain analysiert die Änderung und benachrichtigt den User."""
        on_change = monitor.get("on_change", "notify")
        name = monitor["name"]
        icon = self.TYPE_ICONS.get(monitor.get("type", "custom"), "📡")

        if on_change == "log":
            # Nur loggen, kein Popup
            log.info(f"[MONITOR LOG] {name}: {new_result[:200]}")
            return

        # Brain analysiert was sich geändert hat
        summary = new_result[:600]
        if self._brain:
            try:
                analysis = self._brain.think(
                    f"In 1-2 Sätzen: Was ist neu/interessant in diesen Monitoring-Ergebnissen für '{name}'?\n\n{new_result[:1500]}",
                    max_iterations=1,
                    depth=2,
                    isolated=True
                )
                summary = analysis[:300] if analysis else summary
            except Exception:
                pass

        # UI Notification
        if self._notify:
            try:
                self._notify(f"{icon} {name}", summary)
            except Exception:
                pass

        # Bei "act": Brain soll selbst reagieren
        if on_change == "act" and self._brain:
            try:
                self._brain.think(
                    f"[MONITOR ALERT] '{name}' hat sich geändert.\n\nNeue Daten:\n{new_result[:2000]}\n\n"
                    f"Reagiere darauf: {monitor.get('action_prompt', 'Informiere den User und handle wenn nötig.')}",
                    max_iterations=5,
                    depth=3,
                    isolated=True
                )
            except Exception as e:
                log.error(f"Monitor act failed: {e}")

    # ── Status ────────────────────────────────────────────────

    def get_status_summary(self) -> str:
        """Kurze Übersicht für Sidebar."""
        monitors = self.list_monitors()
        if not monitors:
            return "No monitors configured."

        active   = sum(1 for m in monitors if m["status"] == "active")
        paused   = sum(1 for m in monitors if m["status"] == "paused")
        changed  = sum(1 for m in monitors if m.get("change_count", 0) > 0)

        lines = [f"{active} active, {paused} paused, {changed} with changes"]
        now = datetime.now()

        for m in sorted(monitors, key=lambda x: x.get("next_check") or ""):
            icon   = self.TYPE_ICONS.get(m.get("type", "custom"), "📡")
            status = "⏸" if m["status"] == "paused" else "●"
            last   = m.get("last_checked")
            last_str = datetime.fromisoformat(last).strftime("%H:%M") if last else "never"
            changes = m.get("change_count", 0)
            chg_str = f" ⚡{changes}" if changes > 0 else ""
            lines.append(f"{status} {icon} {m['name']}  [{m['interval_minutes']}min | last: {last_str}{chg_str}]")

        return "\n".join(lines)

    def force_check_all(self):
        """Erzwingt sofortigen Check aller aktiven Monitors."""
        with self._lock:
            for mid, m in self.monitors.items():
                if m["status"] == "active":
                    m["next_check"] = datetime.now().isoformat()
            self._save()
