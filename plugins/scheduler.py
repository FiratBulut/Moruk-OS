"""
Moruk OS - Scheduler Plugin v2
Geplante Tasks: Führt Aktionen zu bestimmten Zeiten aus.
"""

PLUGIN_NAME = "scheduler"
PLUGIN_CORE = False
PLUGIN_DESCRIPTION = "Plant und führt Tasks zu bestimmten Zeiten aus. Unterstützt: Cron-Syntax, Relative Zeit."
PLUGIN_PARAMS = {"action": "schedule|list|cancel|run", "task": "Task-Name", "time": "Zeit (cron oder +Xm, +Xh)", "command": "Befehl oder Plugin-Aufruf"}

import subprocess
import json
import os
import shlex
from datetime import datetime, timedelta

SCHEDULE_FILE = os.path.expanduser("~/moruk-os/data/scheduled_tasks.json")

def _load():
    os.makedirs(os.path.dirname(SCHEDULE_FILE), exist_ok=True)
    if os.path.exists(SCHEDULE_FILE):
        try:
            with open(SCHEDULE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save(data):
    os.makedirs(os.path.dirname(SCHEDULE_FILE), exist_ok=True)
    tmp = SCHEDULE_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, SCHEDULE_FILE)
    except Exception as e:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise e

# Maximale Anzahl geplanter Tasks
MAX_SCHEDULED_TASKS = 10

# Verbotene Befehle (dürfen nie geplant werden)
BLOCKED_COMMANDS = [
    "rm ", "rm	", "rmdir", "rm-rf", "shred", "dd ", "mkfs",
    "chmod 777", "chown", "> /", "truncate", "pkill", "kill ",
    "sudo", "su ", "passwd", "shutdown", "reboot", "halt",
    "write_file", "self_edit",  # Keine Datei-Schreiboperationen
]

def _is_safe_command(command: str) -> tuple[bool, str]:
    """Prüft ob ein Befehl sicher geplant werden darf."""
    cmd_lower = command.strip().lower()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return False, f"Verbotener Befehl: '{blocked}' nicht erlaubt in Scheduler"
    # Nur bekannte sichere Befehle erlauben
    SAFE_PREFIXES = (
        "python3 ", "python ", "pip ", "pip3 ",
        "ls ", "cat ", "grep ", "find ", "echo ",
        "mkdir ", "cp ", "mv ",  # nur kopieren/verschieben erlaubt
        "git ", "curl ", "wget ",
    )
    if not any(cmd_lower.startswith(p) for p in SAFE_PREFIXES):
        return False, f"Befehl nicht in Whitelist. Erlaubt: python3, pip, ls, cat, grep, find, echo, mkdir, cp, mv, git, curl, wget"
    return True, ""

def execute(params):
    action = params.get("action", "list")

    # ── LIST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if action == "list":
        schedule = _load()
        if not schedule:
            return {"success": True, "result": "No scheduled tasks."}
        now = datetime.now()
        lines = ["Scheduled Tasks:", "-" * 40]
        for name, task in schedule.items():
            try:
                run_at = datetime.fromisoformat(task["run_at"])
                if run_at < now and task.get("status") == "pending":
                    status = "OVERDUE"
                else:
                    status = task.get("status", "pending").upper()
                time_str = run_at.strftime("%Y-%m-%d %H:%M")
            except Exception:
                status = task.get("status", "?").upper()
                time_str = task.get("run_at", "?")
            lines.append(f"  [{status}] {name} @ {time_str}")
            lines.append(f"    cmd: {task.get('command', '?')[:60]}")
        return {"success": True, "result": "\n".join(lines)}

    # ── SCHEDULE ━━━━━━━━━━━━━━━━━━━━━━━━━━
    elif action == "schedule":
        task_name = params.get("task", "").strip()
        time_spec  = params.get("time", "").strip()
        command    = params.get("command", "").strip()

        if not task_name or not time_spec or not command:
            return {"success": False, "result": "Provide: task, time (+Xm/+Xh/+Xd), command"}

        # Parse relative time
        if time_spec.startswith("+"):
            try:
                unit   = time_spec[-1].lower()
                amount = int(time_spec[1:-1])
                delta  = {"m": timedelta(minutes=amount),
                          "h": timedelta(hours=amount),
                          "d": timedelta(days=amount)}.get(unit)
                if delta is None:
                    return {"success": False, "result": "Time unit must be m, h, or d"}
                run_at = (datetime.now() + delta).isoformat()
            except ValueError:
                return {"success": False, "result": "Invalid time format. Use +30m, +2h, +1d"}
        else:
            run_at = time_spec  # assume ISO format

        # Safety check vor dem Speichern
        safe, reason = _is_safe_command(command)
        if not safe:
            return {"success": False, "result": f"❌ Scheduler Safety: {reason}"}

        schedule = _load()

        # Max Tasks Limit
        pending = [t for t in schedule.values() if t.get("status") == "pending"]
        if len(pending) >= MAX_SCHEDULED_TASKS:
            return {"success": False, "result": f"❌ Scheduler voll: Max {MAX_SCHEDULED_TASKS} Tasks erlaubt. Erst bestehende abbrechen."}

        schedule[task_name] = {
            "command": command,
            "run_at": run_at,
            "created": datetime.now().isoformat(),
            "status": "pending"
        }
        _save(schedule)
        run_at_fmt = datetime.fromisoformat(run_at).strftime("%Y-%m-%d %H:%M:%S")
        return {"success": True, "result": f"Scheduled '{task_name}' at {run_at_fmt}\nCommand: {command}"}

    # ── CANCEL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    elif action == "cancel":
        task_name = params.get("task", "").strip()
        if not task_name:
            return {"success": False, "result": "Provide 'task' param"}
        schedule = _load()
        if task_name not in schedule:
            return {"success": False, "result": f"Task '{task_name}' not found"}
        del schedule[task_name]
        _save(schedule)
        return {"success": True, "result": f"Cancelled task: {task_name}"}

    # ── RUN (immediate) ━━━━━━━━━━━━━━━━━━━━━━━
    elif action == "run":
        command = params.get("command", "").strip()
        if not command:
            task_name = params.get("task", "").strip()
            if task_name:
                schedule = _load()
                if task_name not in schedule:
                    return {"success": False, "result": f"Task '{task_name}' not found"}
                command = schedule[task_name]["command"]
            else:
                return {"success": False, "result": "Provide 'command' or 'task' param"}
        # Safety check vor Ausführung
        safe, reason = _is_safe_command(command)
        if not safe:
            return {"success": False, "result": f"❌ Scheduler Safety: {reason}"}

        try:
            args = shlex.split(command)
            r = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=60)
            output = r.stdout.strip() or r.stderr.strip() or "(no output)"
            return {"success": r.returncode == 0, "result": f"Ran: {command}\nOutput: {output[:500]}"}
        except subprocess.TimeoutExpired:
            return {"success": False, "result": f"Command timed out after 60s: {command}"}
        except Exception as e:
            return {"success": False, "result": f"Run error: {e}"}

    else:
        return {"success": False, "result": f"Unknown action '{action}'. Use: schedule, list, cancel, run"}
