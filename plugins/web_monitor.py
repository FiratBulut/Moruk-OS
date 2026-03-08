"""
Moruk AI OS - Web Monitor Plugin
Brain kann damit Monitors hinzufügen, entfernen und auflisten.
"""

PLUGIN_NAME = "web_monitor"
PLUGIN_DESCRIPTION = (
    "Monitor websites, search queries, GitHub repos, prices — periodically and automatically. "
    "Actions: add, remove, list, pause, resume, check_now. "
    "Types: search, url, github, price, news. "
    "on_change: notify (popup), log (silent), act (brain reacts automatically)."
)
PLUGIN_PARAMS = (
    '"action": "add|remove|list|pause|resume|check_now", '
    '"name": "Monitor name", '
    '"type": "search|url|github|price|news", '
    '"query": "what to monitor", '
    '"interval_minutes": 60, '
    '"on_change": "notify|log|act"'
)
PLUGIN_CORE = False

from core.logger import get_logger
log = get_logger("web_monitor")

# Von autonomy_loop / main_window gesetzt
_engine = None


def execute(params: dict) -> dict:
    global _engine

    if _engine is None:
        try:
            from core.monitor_engine import MonitorEngine
            _engine = MonitorEngine()
        except Exception as e:
            return {"success": False, "result": f"MonitorEngine not available: {e}"}

    action = params.get("action", "list")

    # ── LIST ──────────────────────────────────────────────────
    if action == "list":
        monitors = _engine.list_monitors()
        if not monitors:
            return {"success": True, "result": "No monitors configured yet.\n\nExamples:\n"
                    "• web_monitor add name='Grok Changelog' type=search query='xAI grok API changelog' interval=120\n"
                    "• web_monitor add name='EUR/USD' type=price query='EUR USD exchange rate' interval=60\n"
                    "• web_monitor add name='moruk-os' type=github query='owner/moruk-os' interval=1440"}

        lines = [f"📡 Active Monitors ({len(monitors)}):"]
        for m in monitors:
            from core.monitor_engine import MonitorEngine
            icon = MonitorEngine.TYPE_ICONS.get(m.get("type", "custom"), "📡")
            status_icon = "⏸" if m["status"] == "paused" else "🟢"
            last = m.get("last_checked", "never")
            if last and last != "never":
                from datetime import datetime
                last = datetime.fromisoformat(last).strftime("%d.%m %H:%M")
            lines.append(
                f"\n{status_icon} {icon} [{m['id']}] {m['name']}\n"
                f"   Type: {m['type']} | Every: {m['interval_minutes']}min | "
                f"Last: {last} | Changes: {m.get('change_count', 0)}\n"
                f"   Query: {m['query'][:60]}\n"
                f"   On change: {m.get('on_change', 'notify')}"
            )
        return {"success": True, "result": "\n".join(lines)}

    # ── ADD ───────────────────────────────────────────────────
    elif action == "add":
        name     = params.get("name", "")
        mtype    = params.get("type", "search")
        query    = params.get("query", "")
        interval = int(params.get("interval_minutes", 60))
        on_change = params.get("on_change", "notify")

        if not name or not query:
            return {"success": False, "result": "Required: name and query"}

        result = _engine.add_monitor(name, mtype, query, interval, on_change)
        if result["success"]:
            return {
                "success": True,
                "result": (
                    f"✅ Monitor added: '{name}'\n"
                    f"   Type: {mtype} | Interval: {interval}min | On change: {on_change}\n"
                    f"   First check will run within {min(interval, 60)} minutes."
                )
            }
        return {"success": False, "result": result.get("error", "Failed")}

    # ── REMOVE ────────────────────────────────────────────────
    elif action == "remove":
        monitor_id = params.get("id") or params.get("name", "")
        result = _engine.remove_monitor(monitor_id)
        if result["success"]:
            return {"success": True, "result": f"🗑 Removed: {result['removed']}"}
        return {"success": False, "result": result.get("error", "Not found")}

    # ── PAUSE / RESUME ────────────────────────────────────────
    elif action == "pause":
        mid = params.get("id") or params.get("name", "")
        r = _engine.pause_monitor(mid)
        return {"success": r["success"], "result": f"⏸ Paused: {mid}" if r["success"] else r.get("error")}

    elif action == "resume":
        mid = params.get("id") or params.get("name", "")
        r = _engine.resume_monitor(mid)
        return {"success": r["success"], "result": f"▶ Resumed: {mid}" if r["success"] else r.get("error")}

    # ── CHECK NOW ─────────────────────────────────────────────
    elif action == "check_now":
        mid = params.get("id") or params.get("name")
        if mid:
            with _engine._lock:
                if mid in _engine.monitors:
                    from datetime import datetime
                    _engine.monitors[mid]["next_check"] = datetime.now().isoformat()
                    _engine._save()
            return {"success": True, "result": f"⚡ Check triggered for: {mid}"}
        else:
            _engine.force_check_all()
            return {"success": True, "result": "⚡ Check triggered for all monitors"}

    return {"success": False, "result": f"Unknown action: {action}. Use: add|remove|list|pause|resume|check_now"}
