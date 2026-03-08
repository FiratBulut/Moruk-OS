"""
Moruk AI OS - Memory System v3.1
Short-term: JSON (session). Long-term: VectorMemory (SQLite + TF-IDF).
"""
import json
import os
from datetime import datetime
from pathlib import Path
from core.vector_memory import VectorMemory

DATA_DIR = Path(__file__).parent.parent / "data"

class Memory:
    def __init__(self):
        self.short_path = DATA_DIR / "memory_short.json"
        self.short_term = self._load_short()
        self.vector = VectorMemory()

    def _load_short(self) -> list:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if self.short_path.exists():
            try:
                with open(self.short_path, "r") as f:
                    return json.load(f)
            except: pass
        return []

    def _save_short(self):
        tmp_path = self.short_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.short_term, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.short_path)

    def remember_short(self, content: str, category: str = "general"):
        self.short_term.append({"content": content, "category": category, "timestamp": datetime.now().isoformat()})
        self.short_term = self.short_term[-50:]
        self._save_short()

    def clear_short_term(self):
        self.short_term = []
        self._save_short()

    def store(self, content: str, metadata: dict = None):
        cat = metadata.get("category", "learned") if metadata else "learned"
        tags = metadata.get("tags", []) if metadata else []
        self.remember_long(content, category=cat, tags=tags)

    def remember_long(self, content: str, category: str = "learned", tags: list = None):
        self.vector.store(content, category=category, tags=tags)

    def get_long_term(self, limit: int = 30) -> list:
        return self.vector.get_recent(limit=limit)

    def search_long(self, keyword: str) -> list:
        return self.vector.search(keyword)

    def get_stats(self) -> dict:
        v = self.vector.get_stats()
        return {
            "short_term_count": len(self.short_term),
            "long_term_count": v["total_memories"],
            "categories": v["categories"],
            "all_tags": v.get("all_tags", [])
        }

    def get_memory_context(self, query: str = "", max_entries: int = 10) -> str:
        """Gibt relevante Erinnerungen als Kontext-String zurück."""
        parts = []

        # Relevante Langzeit-Erinnerungen via TF-IDF Suche
        if query:
            results = self.vector.search(query, max_results=max_entries, min_score=0.1)
            if results:
                parts.append("Relevant Memory:")
                for r in results[:5]:
                    parts.append(f"  • [{r['category']}] {r['content'][:150]}")

        # Neueste Langzeit-Erinnerungen (falls keine Suche oder wenig Treffer)
        if not parts:
            recent = self.vector.get_recent(limit=5)
            if recent:
                parts.append("Recent Memory:")
                for r in recent:
                    parts.append(f"  • {r['content'][:150]}")

        # Kurzzeit-Gedächtnis (letzte 3)
        if self.short_term:
            parts.append("Short-term:")
            for m in self.short_term[-3:]:
                parts.append(f"  • [{m['category']}] {m['content'][:100]}")

        return "\n".join(parts) if parts else ""

    def index_codebase(self, codebase_dir: str = None, extensions: list = None):
        """Indexiert Python-Dateien. Löscht zuerst den alten Codebase-Index."""
        from pathlib import Path as _Path
        base = _Path(codebase_dir) if codebase_dir else _Path(__file__).parent.parent
        exts = extensions or [".py"]
        if hasattr(self.vector, "clear_category"):
            self.vector.clear_category("codebase")
        indexed = 0
        for ext in exts:
            for fpath in base.rglob(f"*{ext}"):
                parts_set = set(fpath.parts)
                if any(x in parts_set for x in ("venv", "__pycache__", ".git", "node_modules")):
                    continue
                try:
                    code = fpath.read_text(encoding="utf-8", errors="replace")
                    rel = str(fpath.relative_to(base))
                    summary = f"FILE: {rel}\n{code[:2000]}"
                    self.vector.store(summary, category="codebase", tags=["code", ext.lstrip(".")])
                    indexed += 1
                except Exception:
                    continue
        return indexed

    def search_codebase(self, query: str, max_results: int = 5) -> list:
        """Sucht nur im Codebase-Index."""
        return self.vector.search(query, max_results=max_results, category="codebase")
