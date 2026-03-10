"""Moruk OS - Media Control Plugin"""

PLUGIN_NAME = "media_control"
PLUGIN_DESCRIPTION = "Control media playback and volume: play, pause, stop, next, prev, volume_up, volume_down, mute, get_volume."
PLUGIN_PARAMS = ["action", "value"]

import subprocess
import shutil
import os
import re


def _run(cmd_list, timeout=5):
    try:
        r = subprocess.run(
            cmd_list, shell=False, capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip(), r.returncode == 0
    except Exception as e:
        return str(e), False


def execute(params):
    action = params.get("action", "get_volume")
    value = params.get("value", None)

    os.environ.setdefault("DISPLAY", ":0")

    try:
        # === Playback controls via playerctl ===
        if action in (
            "play",
            "pause",
            "play-pause",
            "stop",
            "next",
            "prev",
            "previous",
        ):
            if action == "prev":
                action = "previous"
            if shutil.which("playerctl"):
                out, ok = _run(["playerctl", action])
                if ok:
                    return {"success": True, "result": f"Media: {action}"}

            # Fallback: xdotool key
            key_map = {
                "play-pause": "XF86AudioPlay",
                "play": "XF86AudioPlay",
                "pause": "XF86AudioPause",
                "stop": "XF86AudioStop",
                "next": "XF86AudioNext",
                "previous": "XF86AudioPrev",
            }
            if shutil.which("xdotool") and action in key_map:
                _run(["xdotool", "key", key_map[action]])
                return {"success": True, "result": f"Media key: {action}"}
            return {"success": False, "result": "Media control tool not found."}

        elif action == "status":
            if shutil.which("playerctl"):
                status, _ = _run(["playerctl", "status"])
                meta, _ = _run(
                    [
                        "playerctl",
                        "metadata",
                        "--format",
                        "{{playerName}}: {{title}} - {{artist}}",
                    ]
                )
                return {"success": True, "result": f"Status: {status}\n{meta}"}
            return {"success": True, "result": "No active media player"}

        # === Volume controls ===
        elif action == "get_volume":
            vol_out, ok = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
            if ok:
                m = re.search(r"([0-9]+)%", vol_out)
                if m:
                    mute_out, _ = _run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
                    mute_str = " 🔇 MUTED" if "yes" in mute_out.lower() else ""
                    return {
                        "success": True,
                        "result": f"Volume: {m.group(1)}%{mute_str}",
                    }
            return {"success": False, "result": "Cannot get volume"}

        elif action == "volume_up":
            step = f"+{int(value) if value else 5}%"
            _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", step])
            return {"success": True, "result": f"Volume increased"}

        elif action == "volume_down":
            step = f"-{int(value) if value else 5}%"
            _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", step])
            return {"success": True, "result": f"Volume decreased"}

        elif action == "set_volume":
            if value is None:
                return {"success": False, "result": "Need 'value' (0-150)"}
            vol = max(0, min(150, int(value)))
            _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{vol}%"])
            return {"success": True, "result": f"Volume set to {vol}%"}

        elif action == "mute":
            _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
            mute_out, _ = _run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
            state = "🔇 Muted" if "yes" in mute_out.lower() else "🔊 Unmuted"
            return {"success": True, "result": state}

        else:
            return {"success": False, "result": f"Unknown action: {action}"}

    except Exception as e:
        return {"success": False, "result": f"Media control error: {e}"}
