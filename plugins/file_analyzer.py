"""
Moruk OS - File Analyzer Plugin v2
Analysiert Dateien: Größe, Typ, Wortanzahl, Code-Zeilen.
"""

PLUGIN_CORE = True
PLUGIN_NAME = "file_analyzer"
PLUGIN_DESCRIPTION = (
    "Analysiert Dateien: Größe, Typ, Zeilenanzahl, Wortanzahl, Code-Metriken."
)
PLUGIN_PARAMS = {"path": "Pfad zur Datei oder Verzeichnis"}

import os
import mimetypes
from pathlib import Path
from datetime import datetime


def execute(params):
    path = params.get("path", "")
    if not path:
        return {"success": False, "result": "No path provided"}

    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return {"success": False, "result": f"Path does not exist: {path}"}

    lines_out = []

    if os.path.isfile(path):
        stat = os.stat(path)
        size_kb = stat.st_size / 1024
        mime = mimetypes.guess_type(path)[0] or "unknown"
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        lines_out.append(f"File:      {path}")
        lines_out.append(f"Size:      {size_kb:.1f} KB ({stat.st_size} bytes)")
        lines_out.append(f"MIME:      {mime}")
        lines_out.append(f"Modified:  {mtime}")

        ext = Path(path).suffix.lower()
        code_exts = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".cpp": "C++",
            ".c": "C",
            ".java": "Java",
            ".go": "Go",
            ".rs": "Rust",
            ".sh": "Shell",
            ".json": "JSON",
            ".yaml": "YAML",
            ".md": "Markdown",
            ".html": "HTML",
            ".css": "CSS",
        }
        lang = code_exts.get(ext, "Text/Binary")
        lines_out.append(f"Language:  {lang}")

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            n_lines = len(content.splitlines())
            n_words = len(content.split())
            n_chars = len(content)
            # Count code lines (non-empty, non-comment)
            if lang in (
                "Python",
                "JavaScript",
                "TypeScript",
                "C++",
                "C",
                "Java",
                "Go",
                "Rust",
                "Shell",
            ):
                code_lines = sum(
                    1
                    for l in content.splitlines()
                    if l.strip() and not l.strip().startswith(("#", "//", "*", "/*"))
                )
                lines_out.append(f"Lines:     {n_lines} total / {code_lines} code")
            else:
                lines_out.append(f"Lines:     {n_lines}")
            lines_out.append(f"Words:     {n_words}")
            lines_out.append(f"Chars:     {n_chars}")
        except Exception:
            lines_out.append("Content:   (binary or unreadable)")

    elif os.path.isdir(path):
        skip = {"venv", "venv_xtts", "__pycache__", ".git", "node_modules", ".cache"}
        file_list = []
        total_size = 0
        ext_counts = {}
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in skip]
            for f in files:
                fp = os.path.join(root, f)
                try:
                    sz = os.path.getsize(fp)
                    total_size += sz
                    file_list.append(fp)
                    ext = Path(f).suffix.lower() or "(no ext)"
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
                except Exception:
                    pass

        total_kb = total_size / 1024
        total_mb = total_kb / 1024
        lines_out.append(f"Directory: {path}")
        lines_out.append(f"Files:     {len(file_list)}")
        lines_out.append(f"Size:      {total_mb:.2f} MB ({total_kb:.0f} KB)")

        if ext_counts:
            top = sorted(ext_counts.items(), key=lambda x: -x[1])[:8]
            lines_out.append("Top types: " + ", ".join(f"{e}({c})" for e, c in top))

    return {"success": True, "result": "\n".join(lines_out)}
