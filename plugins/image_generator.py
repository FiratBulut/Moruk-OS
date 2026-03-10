import requests
import json
import base64
import os
from datetime import datetime
from pathlib import Path

PLUGIN_NAME = "image_generator"
PLUGIN_CORE = False
PLUGIN_DESCRIPTION = (
    "Generiert Bilder basierend auf einem Text-Prompt mithilfe der Gemini/Imagen API."
)
PLUGIN_PARAMS = {
    "prompt": "Der Text-Prompt, der das zu generierende Bild beschreibt.",
    "model": "Das zu verwendende Modell (optional, default: imagen-4.0-generate-001)",
}

CONFIG_DIR = Path(__file__).parent.parent / "config"
DATA_DIR = Path(__file__).parent.parent / "data"
IMAGES_DIR = DATA_DIR / "images"


def _load_vision_settings():
    """Liest vision_api_key, vision_model und vision_base_url aus user_settings.json."""
    for path in [CONFIG_DIR / "user_settings.json", CONFIG_DIR / "settings.json"]:
        if path.exists():
            try:
                with open(path, "r") as f:
                    s = json.load(f)
                api_key = s.get("vision_api_key") or ""  # Kein Fallback auf api_key!
                model = s.get("vision_model") or ""
                base_url = s.get("vision_base_url") or ""
                if api_key:
                    return api_key, model, base_url
            except Exception:
                pass
    return None, None, None


def _load_api_key():
    api_key, _, __ = _load_vision_settings()
    return api_key


def execute(params):
    prompt = params.get("prompt")

    if not prompt:
        return {"success": False, "result": "Fehler: Kein Prompt angegeben."}

    api_key, settings_model, settings_base_url = _load_vision_settings()
    # Priorität: 1. params model, 2. vision_model aus Settings, 3. Default
    model = params.get("model") or settings_model or "imagen-4.0-generate-001"
    base_url = params.get("base_url") or settings_base_url or ""

    if not api_key:
        return {
            "success": False,
            "result": "Fehler: Kein API-Key für Vision/Imagen in Settings gefunden. Bitte Vision Slot konfigurieren.",
        }

    # API-Version bestimmen:
    # gemini-3-pro-image und gemini-3.1-flash-image brauchen v1alpha
    # Imagen und ältere Gemini → v1beta
    needs_alpha = any(
        x in model.lower()
        for x in [
            "gemini-3-pro-image",
            "gemini-3.1-flash-image",
            "gemini-3-flash-image",
        ]
    )
    # API-Version: needs_alpha hat immer Vorrang — auch wenn base_url gesetzt ist
    if needs_alpha:
        api_base = "https://generativelanguage.googleapis.com/v1alpha"
    elif base_url:
        # Nur für nicht-alpha Modelle die eigene Base URL benutzen
        api_base = base_url.rstrip("/")
        # /openai/ Suffix entfernen falls vorhanden (nur für Chat, nicht Image)
        api_base = api_base.replace("/openai", "")
    else:
        api_base = "https://generativelanguage.googleapis.com/v1beta"

    # Modell-Typ bestimmen
    is_imagen = "imagen" in model.lower()
    # Gemini 3 Pro Image / 2.x Flash Image → generateContent mit response_modalities
    is_gemini_image = any(
        x in model.lower()
        for x in [
            "gemini-3-pro-image",
            "gemini-2.5-flash-image",
            "gemini-3.1-flash-image",
            "flash-image",
            "pro-image",
        ]
    )

    if is_imagen:
        url = f"{api_base}/models/{model}:predict?key={api_key}"
        payload = {"instances": [{"prompt": prompt}]}
    else:
        # Gemini native image generation (gemini-3-pro-image-preview etc.)
        url = f"{api_base}/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }

    try:
        response = requests.post(url, json=payload, timeout=120)
        if response.status_code != 200:
            return {
                "success": False,
                "result": f"API Fehler {response.status_code}: {response.text[:300]}",
            }
        data = response.json()

        image_data = None

        # Imagen :predict Response
        if "predictions" in data:
            for pred in data.get("predictions", []):
                image_data = pred.get("bytesBase64Encoded") or pred.get(
                    "image", {}
                ).get("imageBytes")
                if image_data:
                    break

        # Gemini generateContent Response (inline_data)
        elif "candidates" in data:
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        image_data = part["inlineData"].get("data")
                    elif "inline_data" in part:
                        image_data = part["inline_data"].get("data")
                    if image_data:
                        break

        if not image_data:
            # Debug: zeige was zurückgekommen ist
            snippet = str(data)[:400]
            return {
                "success": False,
                "result": f"Keine Bilddaten erhalten (Model: {model})\nAPI Response: {snippet}",
            }

        # Verzeichnis erstellen
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)

        # Datei speichern
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Gemini_Generated_Image_{timestamp}.png"
        filepath = IMAGES_DIR / filename

        with open(filepath, "wb") as f:
            f.write(base64.b64decode(image_data))

        return {
            "success": True,
            "result": f"Bild erfolgreich generiert und gespeichert: {filepath}\n\n![Generated Image]({filepath})",
        }

    except Exception as e:
        return {"success": False, "result": f"Fehler bei der Bildgenerierung: {str(e)}"}
