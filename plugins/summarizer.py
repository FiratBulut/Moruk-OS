"""
Moruk OS - Summarizer Plugin v3
Nutzt Brain/LLM direkt zum Zusammenfassen — kein ML-Download nötig.
Fallback auf einfache Extraktion wenn Brain nicht verfügbar.
"""

PLUGIN_NAME = "summarizer"
PLUGIN_DESCRIPTION = "Summarize long text into concise summaries. Uses the LLM directly — no ML model download needed."
PLUGIN_PARAMS = (
    '{"text": "text to summarize", "max_length": 150, "style": "bullet|paragraph|tldr"}'
)
PLUGIN_CORE = True

from core.logger import get_logger

log = get_logger("summarizer")

# Von ToolRouter gesetzt
_brain = None


def execute(params: dict) -> dict:
    text = params.get("text", "").strip()
    max_length = int(params.get("max_length", 150))
    style = params.get("style", "paragraph")  # bullet | paragraph | tldr

    if not text:
        return {"success": False, "result": "No text provided"}

    if len(text) < 80:
        return {"success": True, "result": f"(Text too short to summarize)\n\n{text}"}

    # ── LLM Summarization (primär) ────────────────────────────
    if _brain is not None:
        try:
            style_instruction = {
                "bullet": "as 3-5 concise bullet points",
                "paragraph": "as 2-3 concise paragraphs",
                "tldr": "as a single TL;DR sentence (max 2 sentences)",
            }.get(style, "as 2-3 concise paragraphs")

            prompt = (
                f"Summarize the following text {style_instruction}. "
                f"Keep it under {max_length} words. "
                f"Respond only with the summary, no preamble.\n\n"
                f"TEXT:\n{text[:6000]}"
            )

            result = _brain.think(prompt, max_iterations=1, depth=2, isolated=True)

            if result:
                return {
                    "success": True,
                    "result": f"Summary ({style}):\n\n{result.strip()}",
                    "summary": result.strip(),
                    "original_length": len(text),
                    "method": "llm",
                }
        except Exception as e:
            log.warning(f"LLM summarization failed: {e} — falling back to extraction")

    # ── Fallback: Extraktion (erste + letzte Sätze) ───────────
    try:
        import re

        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

        if len(sentences) <= 3:
            summary = " ".join(sentences)
        else:
            # Erste 2 + letzte 1 Sätze
            summary = " ".join(sentences[:2] + ["..."] + sentences[-1:])

        # Auf max_length kürzen
        words = summary.split()
        if len(words) > max_length:
            summary = " ".join(words[:max_length]) + "..."

        return {
            "success": True,
            "result": f"Summary (extraction):\n\n{summary}",
            "summary": summary,
            "original_length": len(text),
            "method": "extraction",
        }
    except Exception as e:
        return {"success": False, "result": f"Summarizer error: {e}"}
