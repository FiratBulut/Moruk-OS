PLUGIN_NAME = 'video'
PLUGIN_DESCRIPTION = (
    'Universal Video Plugin. '
    'Generierung: fal.ai (Veo, Wan, Sora), OpenAI. '
    'Analyse: Frames extrahieren, summarize. '
    'Params: mode (generate|frames|summarize), prompt, path, provider, model, num_frames, duration.'
)
PLUGIN_PARAMS = ['mode', 'prompt', 'path', 'provider', 'model', 'num_frames', 'duration']

import os
import json
import time
import urllib.request
from pathlib import Path

try:
    import cv2
    _cv2_available = True
except ImportError:
    _cv2_available = False

PROJECT_ROOT = Path(__file__).parent.parent
SETTINGS_PATH = PROJECT_ROOT / "config" / "user_settings.json"
OUTPUT_DIR = Path.home() / 'moruk-os' / 'videos'
FRAMES_DIR = Path.home() / 'moruk-os' / 'video_frames'


def _load_video_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            s = json.load(f)
        return {
            "provider": s.get("video_provider", "fal").lower(),
            "api_key":  s.get("video_api_key", "") or s.get("api_key", ""),
            "model":    s.get("video_model", ""),
        }
    except Exception:
        return {"provider": "fal", "api_key": "", "model": ""}


def _generate_fal(prompt: str, model: str, api_key: str, duration: int) -> dict:
    """fal.ai - unterstuetzt Veo2, Wan, CogVideoX, LTX etc."""
    if not api_key:
        return {"success": False, "result": "fal.ai: kein API Key (video_api_key in Settings)"}
    if not model:
        model = "fal-ai/wan/v2.1/1.3b"

    url = f"https://queue.fal.run/{model}"
    payload = json.dumps({"prompt": prompt, "duration": duration, "aspect_ratio": "16:9"}).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Key {api_key}"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        request_id = result.get("request_id")
        if not request_id:
            return {"success": False, "result": f"fal.ai: kein request_id — {result}"}

        # Pollen bis fertig (max 3 Minuten)
        for _ in range(36):
            time.sleep(5)
            req2 = urllib.request.Request(
                f"https://queue.fal.run/{model}/requests/{request_id}/status",
                headers={"Authorization": f"Key {api_key}"}
            )
            with urllib.request.urlopen(req2, timeout=10) as r:
                status = json.loads(r.read())
            if status.get("status") == "COMPLETED":
                break
            if status.get("status") == "FAILED":
                return {"success": False, "result": f"fal.ai Job failed: {status}"}

        req3 = urllib.request.Request(
            f"https://queue.fal.run/{model}/requests/{request_id}",
            headers={"Authorization": f"Key {api_key}"}
        )
        with urllib.request.urlopen(req3, timeout=10) as r:
            final = json.loads(r.read())

        video_url = (final.get("video", {}).get("url") or
                     final.get("output", {}).get("video", {}).get("url") or "")
        if not video_url:
            return {"success": False, "result": f"fal.ai: kein Video-URL — {final}"}

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"video_{int(time.time())}.mp4"
        urllib.request.urlretrieve(video_url, str(out_path))
        return {"success": True, "result": f"Video gespeichert: {out_path}", "path": str(out_path), "url": video_url}
    except Exception as e:
        return {"success": False, "result": f"fal.ai error: {e}"}


def _get_google_token() -> str:
    """Holt Google OAuth2 Token via gcloud oder Application Default Credentials."""
    import subprocess
    # Methode 1: gcloud CLI
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    # Methode 2: google-auth library
    try:
        import google.auth
        import google.auth.transport.requests
        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token
    except Exception:
        pass
    return ""


def _generate_google_veo(prompt: str, model: str, api_key: str, duration: int) -> dict:
    """Google Veo via AI Studio API — nutzt API Key, kein OAuth2/Vertex nötig."""
    # API Key aus Parameter oder Settings
    key = api_key
    if not key:
        try:
            with open(SETTINGS_PATH, "r") as f:
                s = json.load(f)
            key = s.get("video_api_key", "") or s.get("tts_api_key", "") or s.get("api_key", "")
        except Exception:
            pass

    if not key:
        return {"success": False, "result": "Google Veo: kein API Key (video_api_key in Settings eintragen)"}

    if not model:
        model = "veo-3.1-fast-generate-preview"

    # AI Studio API — gleicher Key wie TTS, kein Vertex/OAuth2
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predictLongRunning?key={key}"

    payload = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {
            "durationSeconds": duration,
            "aspectRatio": "16:9",
            "sampleCount": 1,
        }
    }).encode()

    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())

        op_name = result.get("name", "")
        if not op_name:
            return {"success": False, "result": f"Veo: kein Operation Name — {result}"}

        # Operation pollen (max 5 Minuten)
        op_url = f"https://generativelanguage.googleapis.com/v1beta/{op_name}?key={key}"
        op = {}
        for _ in range(60):
            time.sleep(5)
            req2 = urllib.request.Request(op_url)
            with urllib.request.urlopen(req2, timeout=10) as r:
                op = json.loads(r.read())
            if op.get("done"):
                break

        if not op.get("done"):
            return {"success": False, "result": "Veo: Timeout nach 5 Minuten"}
        if op.get("error"):
            return {"success": False, "result": f"Veo Fehler: {op['error']}"}

        # Video-URI extrahieren
        videos = (op.get("response", {}).get("videos") or
                  op.get("response", {}).get("generatedSamples") or [])
        if not videos:
            return {"success": False, "result": f"Veo: kein Video in Response — {op}"}

        video_url = (videos[0].get("uri") or
                     videos[0].get("video", {}).get("uri", ""))
        if not video_url:
            return {"success": False, "result": f"Veo: kein Video-URI — {videos[0]}"}

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"veo_{int(time.time())}.mp4"
        urllib.request.urlretrieve(video_url, str(out_path))
        return {"success": True, "result": f"Veo Video gespeichert: {out_path}", "path": str(out_path)}

    except Exception as e:
        return {"success": False, "result": f"Google Veo error: {e}"}


def _generate_openai(prompt: str, model: str, api_key: str, duration: int) -> dict:
    """OpenAI Sora."""
    if not api_key:
        return {"success": False, "result": "OpenAI: kein API Key"}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.videos.generate(model=model or "sora", prompt=prompt, duration=duration)
        video_url = response.data[0].url if response.data else ""
        if not video_url:
            return {"success": False, "result": "Sora: kein Video-URL"}
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"video_{int(time.time())}.mp4"
        urllib.request.urlretrieve(video_url, str(out_path))
        return {"success": True, "result": f"Sora Video: {out_path}", "path": str(out_path)}
    except Exception as e:
        return {"success": False, "result": f"Sora error: {e}"}


GENERATION_PROVIDERS = {
    "fal":    _generate_fal,
    "fal.ai": _generate_fal,
    "google": _generate_google_veo,
    "veo":    _generate_google_veo,
    "openai": _generate_openai,
    "sora":   _generate_openai,
}


def _analyze_frames(path: str, num_frames: int, mode: str) -> dict:
    if not _cv2_available:
        return {"success": False, "result": "opencv-python fehlt: pip install opencv-python --break-system-packages"}
    if not os.path.exists(path):
        return {"success": False, "result": f"Video nicht gefunden: {path}"}
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, total_frames // num_frames)
    frames = []
    frame_idx = 0
    while len(frames) < num_frames and cap.isOpened():
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if ret:
            jpg_path = FRAMES_DIR / f'frame_{frame_idx:04d}.jpg'
            cv2.imwrite(str(jpg_path), frame)
            frames.append(str(jpg_path))
            frame_idx += step
        else:
            break
    cap.release()
    if mode == 'summarize':
        return {"success": True, "result": f"{len(frames)} Frames aus {os.path.basename(path)} extrahiert.", "frames": frames}
    return {"success": True, "result": f"{len(frames)} Frames: {frames}", "frames": frames}


def execute(params):
    mode = params.get('mode', 'generate').lower()

    if mode in ('frames', 'summarize', 'analyze', 'motion'):
        return _analyze_frames(params.get('path', ''), int(params.get('num_frames', 5)), mode)

    prompt = params.get('prompt', '')
    if not prompt:
        return {"success": False, "result": "mode=generate braucht einen prompt"}

    settings = _load_video_settings()
    provider = (params.get('provider') or settings['provider']).lower()
    api_key  = params.get('api_key')  or settings['api_key']
    model    = params.get('model')    or settings['model']
    duration = int(params.get('duration', 5))

    gen_fn = GENERATION_PROVIDERS.get(provider)
    if not gen_fn:
        return {"success": False, "result": f"Unbekannter Provider: '{provider}'. Verfuegbar: {list(GENERATION_PROVIDERS.keys())}"}

    return gen_fn(prompt, model, api_key, duration)
