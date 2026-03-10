PLUGIN_NAME = "tts"
PLUGIN_DESCRIPTION = "Text-to-Speech using espeak. Params: text, speed(default:120), voice(default:de), pitch(default:60)"
PLUGIN_PARAMS = ["text", "speed", "voice", "pitch"]


def execute(params):
    import subprocess
    import shutil

    text = params.get("text", "")
    if not text:
        return {"success": False, "result": "No text provided"}

    # Prüfe ob espeak installiert ist
    if not shutil.which("espeak"):
        return {
            "success": False,
            "result": "espeak not installed. Run: sudo apt install espeak",
        }

    speed = str(params.get("speed", "120"))
    voice = params.get("voice", "de")
    pitch = str(params.get("pitch", "60"))

    try:
        result = subprocess.run(
            ["espeak", "-s", speed, "-v", voice, "-p", pitch, text],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return {
                "success": True,
                "result": f"🔊 Spoken (speed={speed}, voice={voice}): {text[:60]}",
            }
        else:
            return {"success": False, "result": f"espeak error: {result.stderr[:200]}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "result": "espeak timeout (>15s)"}
    except Exception as e:
        return {"success": False, "result": f"TTS error: {e}"}
