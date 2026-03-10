PLUGIN_NAME = "gui"
PLUGIN_DESCRIPTION = "GUI/Hardware: screenshot, screen_size, mouse_click(x,y), mouse_move(x,y), type_text(text), key_press(key)."
PLUGIN_PARAMS = ["action", "x", "y", "monitor", "text", "key"]

import os

os.environ.setdefault("DISPLAY", ":0")


def execute(params):
    action = params.get("action", "screen_size")

    # Screenshot
    if action == "screenshot":
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        shot_path = os.path.join(base_dir, "gui_screen.png")
        try:
            import subprocess

            result = subprocess.run(
                ["scrot", shot_path], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and os.path.exists(shot_path):
                size = os.path.getsize(shot_path) // 1024
                return {
                    "success": True,
                    "result": f"Screenshot saved: {shot_path} ({size}KB)",
                }
            # Fallback: mss
            import mss

            with mss.mss() as sct:
                sct.shot(mon=int(params.get("monitor", 1)), output=shot_path)
            return {"success": True, "result": f"Screenshot (mss): {shot_path}"}
        except Exception as e:
            return {"success": False, "result": f"Screenshot failed: {e}"}

    # Screen size - support both 'size' and 'screen_size'
    elif action in ("size", "screen_size"):
        try:
            import mss

            with mss.mss() as sct:
                monitors = []
                for i, m in enumerate(sct.monitors):
                    monitors.append(
                        f"Monitor {i}: {m['width']}x{m['height']} at ({m['left']},{m['top']})"
                    )
                return {"success": True, "result": "\n".join(monitors)}
        except Exception as e:
            return {"success": False, "result": f"Screen size error: {e}"}

    # Mouse click
    elif action in ("click", "mouse_click"):
        try:
            import pyautogui

            x = int(params.get("x", 500))
            y = int(params.get("y", 500))
            pyautogui.click(x, y)
            return {"success": True, "result": f"Clicked at ({x},{y})"}
        except Exception as e:
            return {"success": False, "result": f"Click failed: {e}"}

    # Mouse move
    elif action in ("move", "mouse_move"):
        try:
            import pyautogui

            x = int(params.get("x", 960))
            y = int(params.get("y", 300))
            pyautogui.moveTo(x, y, duration=0.5)
            return {"success": True, "result": f"Mouse moved to ({x},{y})"}
        except Exception as e:
            return {"success": False, "result": f"Move failed: {e}"}

    # Type text
    elif action == "type_text":
        try:
            import pyautogui

            text = params.get("text", "")
            if not text:
                return {"success": False, "result": "No text provided"}
            pyautogui.typewrite(text, interval=0.05)
            return {"success": True, "result": f"Typed: {text[:50]}"}
        except Exception as e:
            return {"success": False, "result": f"Type failed: {e}"}

    # Key press
    elif action == "key_press":
        try:
            import pyautogui

            key = params.get("key", "")
            if not key:
                return {"success": False, "result": "No key provided"}
            pyautogui.press(key)
            return {"success": True, "result": f"Key pressed: {key}"}
        except Exception as e:
            return {"success": False, "result": f"Key press failed: {e}"}

    return {
        "success": False,
        "result": f"Unknown action: '{action}'. Use: screenshot, screen_size, mouse_click, mouse_move, type_text, key_press",
    }
