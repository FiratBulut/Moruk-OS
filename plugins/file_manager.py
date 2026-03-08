"""Moruk OS - File Manager Plugin v1.1"""

PLUGIN_NAME = "file_manager"
PLUGIN_DESCRIPTION = "File operations: list, copy, move, delete, mkdir, search, read, info. NOTE: For writing files use write_file tool instead — NOT file_manager(action=write)."
PLUGIN_PARAMS = {"action": "list|copy|move|delete|mkdir|search|read|write|info", "path": "target path", "dest": "destination (for copy/move)", "pattern": "search pattern", "content": "content for write"}

import os
import shutil
from datetime import datetime

# Dirs to skip in search
_SKIP_DIRS = {"venv", "venv_xtts", "__pycache__", ".git", "node_modules", ".cache"}

def _fmt_size(b):
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.0f}{unit}"
        b /= 1024
    return f"{b:.1f}TB"

def execute(params):
    action  = params.get("action", "list")
    path    = os.path.expanduser(params.get("path", "~"))
    dest    = os.path.expanduser(params.get("dest", ""))
    pattern = params.get("pattern", "")
    content = params.get("content", "")

    try:
        # LIST
        if action == "list":
            if not os.path.exists(path):
                return {"success": False, "result": f"Path not found: {path}"}
            items = sorted(os.listdir(path))
            dirs  = [i for i in items if os.path.isdir(os.path.join(path, i))]
            files = [i for i in items if os.path.isfile(os.path.join(path, i))]
            lines = [f"📁 {path}  ({len(dirs)} dirs, {len(files)} files)"]
            for d in dirs[:25]:
                lines.append(f"  📂 {d}/")
            for f in files[:30]:
                fp = os.path.join(path, f)
                try:
                    sz    = _fmt_size(os.path.getsize(fp))
                    mtime = datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    sz, mtime = "?", "?"
                lines.append(f"  📄 {f}  ({sz}, {mtime})")
            if len(items) > 55:
                lines.append(f"  ... +{len(items)-55} more")
            return {"success": True, "result": "\n".join(lines)}

        # INFO
        elif action == "info":
            if not os.path.exists(path):
                return {"success": False, "result": f"Not found: {path}"}
            stat  = os.stat(path)
            is_dir = os.path.isdir(path)
            lines = [
                f"Path:        {path}",
                f"Type:        {'Directory' if is_dir else 'File'}",
                f"Size:        {_fmt_size(stat.st_size)}",
                f"Modified:    {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}",
                f"Permissions: {oct(stat.st_mode)[-3:]}",
            ]
            if is_dir:
                count = sum(len(fs) for _, _, fs in os.walk(path))
                lines.append(f"Total files: {count}")
            return {"success": True, "result": "\n".join(lines)}

        # COPY
        elif action == "copy":
            if not dest:
                return {"success": False, "result": "Provide 'dest' param"}
            if not os.path.exists(path):
                return {"success": False, "result": f"Source not found: {path}"}
            if os.path.isdir(path):
                shutil.copytree(path, dest)
            else:
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                shutil.copy2(path, dest)
            return {"success": True, "result": f"Copied: {path} -> {dest}"}

        # MOVE
        elif action == "move":
            if not dest:
                return {"success": False, "result": "Provide 'dest' param"}
            if not os.path.exists(path):
                return {"success": False, "result": f"Source not found: {path}"}
            shutil.move(path, dest)
            return {"success": True, "result": f"Moved: {path} -> {dest}"}

        # DELETE
        elif action == "delete":
            if not os.path.exists(path):
                return {"success": False, "result": f"Not found: {path}"}
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return {"success": True, "result": f"Deleted: {path}"}

        # MKDIR
        elif action == "mkdir":
            os.makedirs(path, exist_ok=True)
            return {"success": True, "result": f"Directory created: {path}"}

        # SEARCH
        elif action == "search":
            if not pattern:
                return {"success": False, "result": "Provide 'pattern' param"}
            base = path if os.path.isdir(path) else os.path.expanduser("~")
            matches = []
            for root, dirs, files in os.walk(base):
                # Skip unwanted dirs in-place
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
                for f in files:
                    if pattern.lower() in f.lower():
                        fp = os.path.join(root, f)
                        try:
                            sz = _fmt_size(os.path.getsize(fp))
                        except Exception:
                            sz = "?"
                        matches.append(f"  {fp}  ({sz})")
                if len(matches) >= 50:
                    break
            if not matches:
                return {"success": True, "result": f"No files matching '{pattern}' in {base}"}
            return {"success": True, "result": f"Found {len(matches)} file(s) matching '{pattern}':\n" + "\n".join(matches)}

        # READ
        elif action == "read":
            if not os.path.isfile(path):
                return {"success": False, "result": f"File not found: {path}"}
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(8000)
            lines_count = text.count("\n")
            return {"success": True, "result": f"--- {path} ({lines_count} lines) ---\n{text}"}

        # WRITE
        elif action == "write":
            if not content:
                return {"success": False, "result": "WRONG TOOL: Use write_file tool to write files, not file_manager(action=write). Example: write_file(path='...', content='...')"}
            # Falls content vorhanden: ausführen aber warnen
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "result": f"Written {len(content)} chars to {path}. NOTE: Use write_file tool instead of file_manager for writing."}

        else:
            return {"success": False, "result": f"Unknown action '{action}'. Use: list, info, copy, move, delete, mkdir, search, read, write"}

    except PermissionError:
        return {"success": False, "result": f"Permission denied: {path}"}
    except Exception as e:
        return {"success": False, "result": f"File manager error: {e}"}
