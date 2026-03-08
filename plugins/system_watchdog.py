"""
Moruk OS – System Watchdog Plugin
Überwacht laufende Prozesse, Crashes und System-Health.
Läuft als Hintergrund-Thread und sendet Alerts via Signal.
"""

import subprocess
import psutil
import threading
import time
import json
import os
from datetime import datetime

PLUGIN_CORE = True
PLUGIN_NAME = "system_watchdog"
PLUGIN_DESCRIPTION = "Überwacht Prozesse und Crashes. Sendet Alerts bei Problemen."
PLUGIN_PARAMS = {
    "action": "start|stop|status|check|list_crashes",
    "process": "Prozessname zum Überwachen (optional)",
    "interval": "Check-Intervall in Sekunden (default: 30)"
}

# Globaler Watchdog-State
_watchdog_thread = None
_watchdog_running = False
_watched_processes = {}   # name -> {pid, start_time, crash_count}
_crash_log = []           # Liste der erkannten Crashes
_alert_callback = None    # Callback: fn(title, message, problem_id)
_check_interval = 30

# Log-Datei
CRASH_LOG_PATH = os.path.expanduser("~/moruk-os/data/crash_log.json")


def set_alert_callback(callback):
    """Registriert einen Callback für Alert-Events.
    callback(title: str, message: str, problem_id: str)
    """
    global _alert_callback
    _alert_callback = callback


def _send_alert(title: str, message: str, problem_id: str = ""):
    """Sendet Alert via Callback oder Desktop-Notification."""
    if _alert_callback:
        _alert_callback(title, message, problem_id)
    else:
        # Fallback: Desktop-Notification
        try:
            subprocess.run([
                "notify-send", "-u", "critical",
                f"Moruk OS: {title}", message
            ], timeout=5)
        except Exception:
            pass


def _log_crash(process_name: str, pid: int, reason: str):
    """Crash in Log-Datei speichern."""
    entry = {
        "time": datetime.now().isoformat(),
        "process": process_name,
        "pid": pid,
        "reason": reason
    }
    _crash_log.append(entry)

    # In Datei schreiben
    os.makedirs(os.path.dirname(CRASH_LOG_PATH), exist_ok=True)
    try:
        existing = []
        if os.path.exists(CRASH_LOG_PATH):
            with open(CRASH_LOG_PATH, "r") as f:
                existing = json.load(f)
        existing.append(entry)
        # Max 100 Einträge
        existing = existing[-100:]
        with open(CRASH_LOG_PATH, "w") as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass


def _check_system_health():
    """Prüft allgemeine System-Health."""
    alerts = []

    # RAM-Check
    ram = psutil.virtual_memory()
    if ram.percent > 90:
        alerts.append({
            "title": "⚠️ RAM kritisch",
            "message": f"RAM-Auslastung bei {ram.percent:.0f}%!\nNur noch {ram.available // 1024 // 1024} MB frei.",
            "problem_id": "high_ram"
        })

    # Disk-Check
    disk = psutil.disk_usage("/")
    if disk.percent > 90:
        alerts.append({
            "title": "⚠️ Festplatte fast voll",
            "message": f"Festplatte zu {disk.percent:.0f}% voll!\nNur noch {disk.free // 1024 // 1024 // 1024} GB frei.",
            "problem_id": "disk_full"
        })

    # CPU-Check (über 5 Sekunden gemessen)
    cpu = psutil.cpu_percent(interval=2)
    if cpu > 95:
        alerts.append({
            "title": "⚠️ CPU überlastet",
            "message": f"CPU-Auslastung bei {cpu:.0f}%!\nSystem könnte einfrieren.",
            "problem_id": "high_cpu"
        })

    return alerts


def _check_watched_processes():
    """Prüft ob überwachte Prozesse noch laufen."""
    alerts = []
    for name, info in list(_watched_processes.items()):
        pid = info.get("pid")
        if pid:
            try:
                proc = psutil.Process(pid)
                if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
                    raise psutil.NoSuchProcess(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Prozess gecrasht!
                _watched_processes[name]["crash_count"] = info.get("crash_count", 0) + 1
                _watched_processes[name]["pid"] = None
                _log_crash(name, pid, "process_not_found")
                alerts.append({
                    "title": f"💥 Prozess gecrasht: {name}",
                    "message": f"Der Prozess '{name}' (PID {pid}) ist nicht mehr aktiv.\n"
                               f"Crash #{_watched_processes[name]['crash_count']} erkannt.",
                    "problem_id": f"crash_{name}"
                })
    return alerts


def _watchdog_loop(interval: int):
    """Haupt-Loop des Watchdogs."""
    # Cooldown pro Problem-ID damit nicht jede Minute ein Alert kommt
    last_alert = {}
    cooldown = 300  # 5 Minuten zwischen gleichen Alerts

    while _watchdog_running:
        try:
            all_alerts = []
            all_alerts.extend(_check_system_health())
            all_alerts.extend(_check_watched_processes())

            now = time.time()
            for alert in all_alerts:
                pid = alert["problem_id"]
                if now - last_alert.get(pid, 0) > cooldown:
                    last_alert[pid] = now
                    _send_alert(alert["title"], alert["message"], pid)

        except Exception:
            pass  # Watchdog darf nie crashen

        time.sleep(interval)


def start_watchdog(interval: int = 30):
    """Startet den Watchdog-Thread."""
    global _watchdog_thread, _watchdog_running, _check_interval
    if _watchdog_running:
        return {"success": True, "result": "Watchdog läuft bereits."}

    _check_interval = interval
    _watchdog_running = True
    _watchdog_thread = threading.Thread(
        target=_watchdog_loop,
        args=(interval,),
        daemon=True,
        name="MorukWatchdog"
    )
    _watchdog_thread.start()
    return {"success": True, "result": f"Watchdog gestartet (Intervall: {interval}s)"}


def stop_watchdog():
    """Stoppt den Watchdog-Thread."""
    global _watchdog_running
    _watchdog_running = False
    return {"success": True, "result": "Watchdog gestoppt."}


def watch_process(name: str, pid: int = None):
    """Fügt einen Prozess zur Überwachung hinzu."""
    if pid is None:
        # PID suchen
        for proc in psutil.process_iter(["pid", "name"]):
            if name.lower() in proc.info["name"].lower():
                pid = proc.info["pid"]
                break

    _watched_processes[name] = {
        "pid": pid,
        "start_time": datetime.now().isoformat(),
        "crash_count": 0
    }
    return {"success": True, "result": f"Überwache '{name}' (PID: {pid})"}


def execute(params: dict) -> dict:
    """Plugin Entry Point."""
    action = params.get("action", "status")
    interval = int(params.get("interval", 30))

    if action == "start":
        result = start_watchdog(interval)
        process = params.get("process")
        if process:
            watch_result = watch_process(process)
            result["result"] += f"\n{watch_result['result']}"
        return result

    elif action == "stop":
        return stop_watchdog()

    elif action == "status":
        status = {
            "running": _watchdog_running,
            "interval": _check_interval,
            "watched_processes": len(_watched_processes),
            "total_crashes_detected": len(_crash_log),
            "processes": _watched_processes
        }
        return {
            "success": True,
            "result": json.dumps(status, indent=2, default=str)
        }

    elif action == "check":
        # Sofortiger Check
        alerts = []
        alerts.extend(_check_system_health())
        alerts.extend(_check_watched_processes())
        if alerts:
            for a in alerts:
                _send_alert(a["title"], a["message"], a["problem_id"])
            return {"success": True, "result": f"{len(alerts)} Probleme gefunden und gemeldet."}
        return {"success": True, "result": "Alles OK. Keine Probleme gefunden."}

    elif action == "list_crashes":
        if not _crash_log:
            return {"success": True, "result": "Keine Crashes aufgezeichnet."}
        return {
            "success": True,
            "result": json.dumps(_crash_log[-10:], indent=2)
        }

    else:
        return {"success": False, "result": f"Unbekannte Action: {action}"}
