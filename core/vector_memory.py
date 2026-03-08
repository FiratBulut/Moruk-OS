import json
import os
import sqlite3
import hashlib
import threading
import unicodedata

import numpy as np
from datetime import datetime
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from core.logger import get_logger

log = get_logger("vector_memory")
DATA_DIR = Path(__file__).parent.parent / "data"


class VectorMemory:
    def __init__(self):
        self.db_path = DATA_DIR / "memory.db"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_db()
        self._vectorizer = TfidfVectorizer()
        self._tfidf_matrix = None
        self._tfidf_ids = []
        self._tfidf_dirty = True

    def _init_db(self):
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, content TEXT, category TEXT,
                tags TEXT, access_count INTEGER DEFAULT 0,
                created_at TEXT, updated_at TEXT
            );
        ''')
        self.conn.commit()

    def _make_id(self, content):
        normalized = unicodedata.normalize("NFC", content).strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]

    def store(self, content, category="learned", tags=None):
        mem_id = self._make_id(content)
        now = datetime.now().isoformat()
        with self._lock:
            matches = self.search(content, max_results=1, min_score=0.9)
            if matches:
                return matches[0]['id']
            self.conn.execute(
                "INSERT OR REPLACE INTO memories (id, content, category, tags, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (mem_id, content, category, json.dumps(tags or []), now, now)
            )
            self.conn.commit()
            self._tfidf_dirty = True
        return mem_id

    def _rebuild_tfidf(self):
        if not self._tfidf_dirty:
            return
        cursor = self.conn.execute("SELECT id, content FROM memories")
        rows = cursor.fetchall()
        if not rows:
            return
        self._tfidf_ids = [r[0] for r in rows]
        contents = [r[1] for r in rows]
        try:
            self._tfidf_matrix = self._vectorizer.fit_transform(contents)
            self._tfidf_dirty = False
        except Exception as e:
            log.warning(f"TF-IDF rebuild failed: {e}")

    def search(self, query: str, max_results: int = 5, min_score: float = 0.1, **kwargs):
        limit = kwargs.get('limit', max_results)
        category_filter = kwargs.get('category', None)  # NEU: optional category filter
        with self._lock:
            self._rebuild_tfidf()
            if self._tfidf_matrix is None or len(self._tfidf_ids) == 0:
                return []
            try:
                query_vec = self._vectorizer.transform([query])
                similarities = cosine_similarity(query_vec, self._tfidf_matrix).flatten()
                results = []
                for idx, score in enumerate(similarities):
                    if score >= min_score:
                        m_id = self._tfidf_ids[idx]
                        row = self.conn.execute(
                            "SELECT content, category, tags FROM memories WHERE id=?", (m_id,)
                        ).fetchone()
                        if row:
                            # Category filter anwenden
                            if category_filter and row[1] != category_filter:
                                continue
                            results.append({
                                "id": m_id,
                                "content": row[0],
                                "category": row[1],
                                "tags": json.loads(row[2] or "[]"),
                                "score": float(score)
                            })
                results.sort(key=lambda x: x['score'], reverse=True)
                return results[:limit]
            except Exception as e:
                log.warning(f"Search failed: {e}")
                return []

    def get_recent(self, limit=5):
        with self._lock:
            try:
                cursor = self.conn.execute(
                    "SELECT id, content, category, tags, created_at FROM memories ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
                results = []
                for r in cursor.fetchall():
                    try:
                        tags = json.loads(r[3])
                    except Exception:
                        tags = []
                    results.append({
                        "id": r[0],
                        "content": r[1],
                        "category": r[2],
                        "tags": tags,
                        "timestamp": r[4]
                    })
                return results
            except Exception as e:
                log.error(f"get_recent failed: {e}")
                return []

    def delete(self, mem_id: str) -> bool:
        """Löscht einen einzelnen Memory-Eintrag."""
        with self._lock:
            cursor = self.conn.execute("DELETE FROM memories WHERE id=?", (mem_id,))
            self.conn.commit()
            if cursor.rowcount > 0:
                self._tfidf_dirty = True
                return True
        return False

    def clear_category(self, category: str) -> int:
        """Löscht alle Einträge einer Kategorie. Nützlich für codebase re-index."""
        with self._lock:
            cursor = self.conn.execute("DELETE FROM memories WHERE category=?", (category,))
            self.conn.commit()
            removed = cursor.rowcount
            if removed > 0:
                self._tfidf_dirty = True
            log.info(f"Cleared {removed} entries from category '{category}'")
            return removed

    def get_stats(self):
        with self._lock:
            try:
                count = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

                # Kategorien dynamisch aus DB laden statt hardcoded ["learned"]
                cat_cursor = self.conn.execute("SELECT DISTINCT category FROM memories WHERE category IS NOT NULL")
                categories = sorted([r[0] for r in cat_cursor.fetchall() if r[0]])

                # Tags aus DB laden
                tags_list = []
                for (raw_tags,) in self.conn.execute("SELECT tags FROM memories WHERE tags IS NOT NULL"):
                    try:
                        parsed = json.loads(raw_tags)
                        tags_list.extend(parsed if isinstance(parsed, list) else [str(parsed)])
                    except Exception:
                        tags_list.extend([x.strip() for x in raw_tags.split(',')])

                all_tags = sorted(set(tags_list))
                db_size = os.path.getsize(self.db_path) / 1024 if os.path.exists(self.db_path) else 0

                return {
                    "total_memories": count,
                    "all_tags": all_tags,
                    "categories": categories,
                    "status": "Healthy",
                    "version": "2.0 (SQLite)",
                    "db_size_kb": round(db_size, 2)
                }
            except Exception as e:
                log.error(f"get_stats failed: {e}")
                return {"total_memories": 0, "all_tags": [], "categories": [], "status": f"Error: {e}", "db_size_kb": 0}
