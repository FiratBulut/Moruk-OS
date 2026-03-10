PLUGIN_CORE = True
PLUGIN_NAME = "voice"
PLUGIN_DESCRIPTION = (
    "Universal TTS Plugin. Unterstützt: piper (lokal), google, elevenlabs, openai. "
    "Provider wird aus user_settings.json gelesen (tts_provider, tts_api_key, tts_model)."
)
PLUGIN_PARAMS = ["text", "length_scale"]

import os
import re
import wave
import json
import logging
import threading
import queue
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("voice")

PROJECT_ROOT = Path(__file__).parent.parent
SETTINGS_PATH = PROJECT_ROOT / "config" / "user_settings.json"
PIPER_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "de_DE-thorsten-high.onnx",
)

_voice_queue = queue.Queue()
_player_thread = None
_thread_lock = threading.Lock()


def _load_tts_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)
        return {
            "provider": settings.get("tts_provider", "piper").lower(),
            "api_key": settings.get("tts_api_key", "") or settings.get("api_key", ""),
            "model": settings.get("tts_model", ""),
            "language": settings.get("tts_language", "de-DE"),
            "voice": settings.get("tts_voice", ""),
        }
    except Exception as e:
        log.warning(f"TTS settings load failed: {e} — using piper")
        return {
            "provider": "piper",
            "api_key": "",
            "model": "",
            "language": "de-DE",
            "voice": "",
        }


def _split_sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?;:])\s+", text.strip())
    result = []
    buffer = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        buffer = (buffer + " " + part).strip() if buffer else part
        if len(buffer) >= 120:
            result.append(buffer)
            buffer = ""
    if buffer:
        result.append(buffer)
    return result if result else [text]


def _play_wav(wav_path: str, duration: float = 10.0):
    timeout = max(60, duration * 3 + 15)
    for cmd in [["paplay", wav_path], ["pw-play", wav_path], ["aplay", "-N", wav_path]]:
        if subprocess.run(["which", cmd[0]], capture_output=True).returncode != 0:
            continue
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        try:
            proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            log.warning(f"{cmd[0]} timeout — killing")
            proc.kill()
            proc.wait()
    log.error("Kein Audio-Player gefunden (paplay, pw-play, aplay)")
    return False


def _play_bytes(audio_bytes: bytes, suffix: str = ".wav"):
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(tmp_fd)
    try:
        with open(tmp_path, "wb") as f:
            f.write(audio_bytes)
        duration = 10.0
        if suffix == ".wav":
            try:
                with wave.open(tmp_path, "rb") as wf:
                    duration = wf.getnframes() / wf.getframerate()
            except Exception:
                pass
        _play_wav(tmp_path, duration)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _speak_piper(text: str, length_scale: float = 1.35):
    try:
        from piper import PiperVoice
        from piper.config import SynthesisConfig
    except ImportError:
        log.error("piper nicht installiert: pip install piper-tts")
        return

    try:
        voice = PiperVoice.load(PIPER_MODEL_PATH)
    except Exception as e:
        log.error(f"Piper model load failed: {e}")
        return

    config = SynthesisConfig(length_scale=length_scale)
    for sentence in _split_sentences(text):
        tmp_fd, wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(tmp_fd)
        try:
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(voice.config.sample_rate)
                for chunk in voice.synthesize(sentence, syn_config=config):
                    wf.writeframes(chunk.audio_int16_bytes)
            with wave.open(wav_path, "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
            _play_wav(wav_path, duration)
        except Exception as e:
            log.error(f"Piper error: {e}")
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass


def _speak_google(text: str, settings: dict):
    """Google Cloud Text-to-Speech API."""
    import urllib.request

    api_key = settings.get("api_key", "")
    language = settings.get("language", "de-DE")
    voice_name = settings.get("voice", "") or settings.get("model", "")

    if not api_key:
        log.error("Google TTS: kein API Key (tts_api_key in Settings)")
        return

    # Default: männliche Wavenet-Stimme — tiefer, professioneller
    voice_config = {"languageCode": language}
    if voice_name:
        voice_config["name"] = voice_name
        voice_config["ssmlGender"] = (
            "MALE" if any(x in voice_name.upper() for x in ("-B", "-D")) else "FEMALE"
        )
    else:
        voice_config["name"] = f"{language}-Wavenet-B"
        voice_config["ssmlGender"] = "MALE"

    try:
        payload = json.dumps(
            {
                "input": {"text": text},
                "voice": voice_config,
                "audioConfig": {
                    "audioEncoding": "LINEAR16",
                    "speakingRate": 0.9,
                    "pitch": -2.0,  # Tiefer = JARVIS-artiger
                },
            }
        ).encode("utf-8")

        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())

        import base64

        audio_bytes = base64.b64decode(result["audioContent"])
        log.info(f"Google TTS: {len(audio_bytes)} bytes, voice={voice_config['name']}")
        _play_bytes(audio_bytes, suffix=".wav")
    except Exception as e:
        log.error(f"Google TTS error: {e}")


def _speak_elevenlabs(text: str, settings: dict):
    """ElevenLabs TTS — beste Qualität, JARVIS-fähig."""
    import urllib.request

    api_key = settings.get("api_key", "")
    # Default: Adam voice (tief, maskulin)
    voice_id = (
        settings.get("voice", "") or settings.get("model", "") or "pNInz6obpgDQGcFmaJgB"
    )

    if not api_key:
        log.error("ElevenLabs: kein API Key (tts_api_key in Settings)")
        return

    try:
        payload = json.dumps(
            {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            data=payload,
            headers={"Content-Type": "application/json", "xi-api-key": api_key},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            audio_bytes = resp.read()
        log.info(f"ElevenLabs TTS: {len(audio_bytes)} bytes")
        _play_bytes(audio_bytes, suffix=".mp3")
    except Exception as e:
        log.error(f"ElevenLabs TTS error: {e}")


def _speak_openai(text: str, settings: dict):
    """OpenAI TTS (tts-1, tts-1-hd) — auch kompatibel mit lokalen Servern."""
    api_key = settings.get("api_key", "")
    model = settings.get("model", "") or "tts-1"
    voice = settings.get("voice", "") or "onyx"  # onyx = tief/maskulin

    if not api_key:
        log.error("OpenAI TTS: kein API Key")
        return

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.audio.speech.create(
            model=model, voice=voice, input=text, response_format="wav"
        )
        log.info(f"OpenAI TTS: '{text[:60]}'")
        _play_bytes(response.content, suffix=".wav")
    except Exception as e:
        log.error(f"OpenAI TTS error: {e}")


# ── Provider Registry ─────────────────────────────────────────
# Neuen Provider hinzufügen: einfach hier eintragen
PROVIDERS = {
    "piper": lambda text, s, ls: _speak_piper(text, ls),
    "google": lambda text, s, ls: _speak_google(text, s),
    "elevenlabs": lambda text, s, ls: _speak_elevenlabs(text, s),
    "eleven": lambda text, s, ls: _speak_elevenlabs(text, s),
    "openai": lambda text, s, ls: _speak_openai(text, s),
    "whisper": lambda text, s, ls: _speak_openai(text, s),
}


def _player_worker():
    while True:
        try:
            item = _voice_queue.get(timeout=60)
            if item is None:
                break

            text, length_scale = item
            settings = _load_tts_settings()
            provider = settings.get("provider", "piper")

            speak_fn = PROVIDERS.get(provider)
            if speak_fn:
                log.info(f"TTS: provider={provider}")
                speak_fn(text, settings, length_scale)
            else:
                log.error(
                    f"Unbekannter TTS Provider: '{provider}'. Verfügbar: {list(PROVIDERS.keys())}"
                )
                _speak_piper(text, length_scale)  # Fallback

            _voice_queue.task_done()

        except queue.Empty:
            continue
        except Exception as e:
            log.error(f"Voice worker error: {e}")
            try:
                _voice_queue.task_done()
            except ValueError:
                pass


def execute(params):
    global _player_thread

    text = params.get("text", "")
    if not text:
        return {"success": False, "result": "No text provided"}

    length_scale = float(params.get("length_scale", 1.35))

    with _thread_lock:
        if _player_thread is None or not _player_thread.is_alive():
            _player_thread = threading.Thread(target=_player_worker, daemon=True)
            _player_thread.start()

    _voice_queue.put((text, length_scale))
    settings = _load_tts_settings()
    return {
        "success": True,
        "result": f"[{settings['provider'].upper()}] Speaking: '{text[:80]}'",
    }
