PLUGIN_NAME = "ml"
PLUGIN_DESCRIPTION = "HF ML: sentiment(text), qa(question,context), zero_shot(text,labels). Torch CPU. Model cached."
PLUGIN_PARAMS = ["task", "text", "question", "context", "labels"]

# Module-level pipeline cache - load once, reuse
_pipelines = {}

def execute(params):

    task = params.get("task", "sentiment")
    text = params.get("text", "")

    try:
        from transformers import pipeline as hf_pipeline

        if task == "sentiment":
            if "sentiment" not in _pipelines:
                _pipelines["sentiment"] = hf_pipeline(
                    "sentiment-analysis",
                    model="distilbert-base-uncased-finetuned-sst-2-english"
                )
            if not text:
                return {"success": False, "result": "No text provided"}
            result = _pipelines["sentiment"](text[:512])
            label = result[0]["label"]
            score = round(result[0]["score"] * 100, 1)
            return {"success": True, "result": f"Sentiment: {label} ({score}% confidence)"}

        elif task == "qa":
            question = params.get("question", text)
            context = params.get("context", "")
            if not question or not context:
                return {"success": False, "result": "Need 'question' and 'context' params"}
            if "qa" not in _pipelines:
                _pipelines["qa"] = hf_pipeline("question-answering")
            result = _pipelines["qa"](question=question, context=context)
            return {"success": True, "result": f"Answer: {result['answer']} (score: {round(result['score'], 3)})"}

        elif task == "zero_shot":
            labels = params.get("labels", [])
            if not text or not labels:
                return {"success": False, "result": "Need 'text' and 'labels' params"}
            if "zero_shot" not in _pipelines:
                _pipelines["zero_shot"] = hf_pipeline("zero-shot-classification")
            result = _pipelines["zero_shot"](text, labels)
            top = result["labels"][0]
            score = round(result["scores"][0] * 100, 1)
            return {"success": True, "result": f"Best label: '{top}' ({score}%)"}

        else:
            return {"success": False, "result": f"Unknown task: {task}. Use: sentiment, qa, zero_shot"}

    except ImportError:
        return {"success": False, "result": "transformers not installed: pip install transformers torch"}
    except Exception as e:
        return {"success": False, "result": f"ML error: {e}"}
