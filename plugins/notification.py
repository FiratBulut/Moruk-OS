PLUGIN_CORE = True
PLUGIN_NAME = "notification"
PLUGIN_DESCRIPTION = "Desktop notifications via notify-send. Params: title, message, urgency(low/normal/critical), timeout(ms)."
PLUGIN_PARAMS = {"title": "Notification title", "message": "Notification body", "urgency": "low|normal|critical", "timeout": "ms (default 5000)"}

import subprocess
import shutil
import os

def execute(params):
    title   = params.get("title", "Moruk OS")
    message = params.get("message", params.get("text", ""))
    urgency = params.get("urgency", "normal")
    timeout = int(params.get("timeout", 5000))

    if not message:
        return {"success": False, "result": "No message provided. Use 'message' param."}

    if urgency not in ("low", "normal", "critical"):
        urgency = "normal"

    os.environ.setdefault("DISPLAY", ":0")
    os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus")

    if shutil.which("notify-send"):
        try:
            r = subprocess.run(
                ["notify-send", "--urgency", urgency, "--expire-time", str(timeout),
                 "--icon", "dialog-information", title, message],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                return {"success": True, "result": f"Notification sent: '{title}' - {message[:80]}"}
        except Exception:
            pass

    if shutil.which("zenity"):
        try:
            dtype = "--error" if urgency == "critical" else "--info"
            subprocess.Popen(["zenity", dtype, "--title", title, "--text", message, "--timeout", "5"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "result": f"Notification sent (zenity): '{title}'"}
        except Exception:
            pass

    return {"success": False, "result": "No notification tool found. Install: sudo apt install libnotify-bin"}
