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
        # Persönliche Infos auch ins User Profile speichern
        if category in ("personal", "preference", "user_info"):
            self._save_to_user_profile(content)

    def _save_to_user_profile(self, content: str):
        """Speichert persönliche Infos in data/user_profile.json unter preferences."""
        profile_path = DATA_DIR / "user_profile.json"
        try:
            profile = {}
            if profile_path.exists():
                with open(profile_path, "r", encoding="utf-8") as f:
                    profile = json.load(f)
            if "preferences" not in profile:
                profile["preferences"] = []
            # Duplikate vermeiden
            if content not in profile["preferences"]:
                profile["preferences"].append(content)
                profile["preferences"] = profile["preferences"][-50:]  # max 50
            tmp = profile_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)
            os.replace(tmp, profile_path)
        except Exception as e:
            pass  # Nie crashen wegen Profil-Speicherfehler

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
        return "Memory Context Active"
