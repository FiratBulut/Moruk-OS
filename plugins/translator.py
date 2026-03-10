"""
Moruk OS - Translator Plugin v2
Machine translation using transformers M2M100.
"""

PLUGIN_NAME = "translator"
PLUGIN_DESCRIPTION = "Translate text between languages using M2M100 model."
PLUGIN_PARAMS = {
    "text": "text to translate",
    "source": "source language (auto for auto-detect)",
    "target": "target language (en, de, fr, es, etc.)",
}

_model = None
_tokenizer = None

# Language name → M2M100 code mapping
LANG_MAP = {
    "german": "de",
    "english": "en",
    "french": "fr",
    "spanish": "es",
    "italian": "it",
    "portuguese": "pt",
    "dutch": "nl",
    "russian": "ru",
    "chinese": "zh",
    "japanese": "ja",
    "arabic": "ar",
    "turkish": "tr",
    "polish": "pl",
    "swedish": "sv",
    "korean": "ko",
}


def _get_model():
    global _model, _tokenizer
    if _model is None:
        from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

        _tokenizer = M2M100Tokenizer.from_pretrained("facebook/m2m100_418M")
        _model = M2M100ForConditionalGeneration.from_pretrained("facebook/m2m100_418M")
    return _model, _tokenizer


def execute(params):
    text = params.get("text", "").strip()
    target = params.get("target", "en").strip().lower()
    source = params.get("source", "auto").strip().lower()

    if not text:
        return {"success": False, "result": "No text provided"}

    # Resolve language names to codes
    target = LANG_MAP.get(target, target)
    if source == "auto" or source == "":
        source = "de"  # Default: German (Moruk's primary language)
    else:
        source = LANG_MAP.get(source, source)

    try:
        import torch

        model, tokenizer = _get_model()
        tokenizer.src_lang = source
        encoded = tokenizer(
            text, return_tensors="pt", padding=True, truncation=True, max_length=512
        )
        with torch.no_grad():
            generated = model.generate(
                **encoded,
                forced_bos_token_id=tokenizer.get_lang_id(target),
                max_length=512,
            )
        translated = tokenizer.batch_decode(generated, skip_special_tokens=True)[0]

        lines = [
            f"Translation ({source} → {target}):",
            f"  Original:    {text[:100]}",
            f"  Translated:  {translated}",
        ]
        return {
            "success": True,
            "result": "\n".join(lines),
            "translation": translated,
            "source_lang": source,
            "target_lang": target,
        }
    except ImportError as e:
        return {
            "success": False,
            "result": f"Missing dependency: {e}\nRun: pip install torch transformers sentencepiece --break-system-packages",
        }
    except Exception as e:
        return {"success": False, "result": f"Translation error: {e}"}
