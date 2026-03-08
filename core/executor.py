"""
Moruk AI OS - Executor
Terminal-Befehle und File-Operationen. (Gehärtet & Syntaktisch korrekt)
"""

import subprocess
import os
import threading
import shlex
from pathlib import Path


class Executor:
    """Führt System-Befehle und File-Ops für Moruk OS aus."""

    def __init__(self, working_dir: str = None):
        self.working_dir = working_dir or str(Path(__file__).parent.parent.resolve())
        self._last_result_lock = threading.Lock()
        self._last_result = None
        self._setup_env()

    @property
    def last_result(self) -> dict:
        with self._last_result_lock:
            return self._last_result

    @last_result.setter
    def last_result(self, value: dict):
        with self._last_result_lock:
            self._last_result = value

    def _setup_env(self):
        """Bereitet die Umgebung vor (venv + PYTHONPATH Injection)."""
        self.env = os.environ.copy()

        venv_dir = os.path.join(self.working_dir, "venv")
        venv_bin = os.path.join(venv_dir, "bin")

        if os.path.isdir(venv_bin):
            self.env["VIRTUAL_ENV"] = venv_dir
            path = self.env.get("PATH", "")
            if venv_bin not in path:
                self.env["PATH"] = venv_bin + os.pathsep + path
            self.env.pop("PYTHONHOME", None)

        pythonpath_parts = [self.working_dir]
        if os.path.isdir(venv_dir):
            lib_dir = os.path.join(venv_dir, "lib")
            if os.path.isdir(lib_dir):
                for py_dir in os.listdir(lib_dir):
                    if py_dir.startswith("python"):
                        sp = os.path.join(lib_dir, py_dir, "site-packages")
                        if os.path.isdir(sp):
                            pythonpath_parts.append(sp)

        old_pp = self.env.get("PYTHONPATH", "")
        if old_pp:
            for p in old_pp.split(os.pathsep):
                if p and p not in pythonpath_parts:
                    pythonpath_parts.append(p)
        
        # HIER IST DIE KORREKTE EINRÜCKUNG, DIE MORUK VORHIN VERMASSELT HAT:
        self.env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    def _is_safe_path(self, path: str) -> bool:
        """Sicherheits-Check: Ist der Pfad innerhalb der Sandbox?"""
        try:
            target_path = Path(path).expanduser().resolve()
            working_dir_path = Path(self.working_dir).resolve()
            return target_path.is_relative_to(working_dir_path)
        except Exception:
            return False

    def run_command(self, command: str, timeout: int = 60) -> dict:
        """Führt einen Bash-Befehl sicher aus (Ohne shell=True)."""
        try:
            # Tilde expandieren: ~ → /home/user (shell=False macht das nicht automatisch)
            home = os.path.expanduser("~")
            command = command.replace(" ~/", f" {home}/").replace(" ~", f" {home}")
            if command.startswith("~/"):
                command = home + "/" + command[2:]
            elif command.startswith("~"):
                command = home + command[1:]

            # FIX 2.1: Befehl in Liste umwandeln, um Injections zu verhindern
            args = shlex.split(command)
            if not args:
                return {"success": False, "error": "Empty command"}

            result = subprocess.run(
                args,
                shell=False,  # <--- SICHER!
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_dir,
                env=self.env
            )
            r = {
                "command": command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            r = {"command": command, "stdout": "", "stderr": f"Timeout after {timeout}s", "returncode": -1, "success": False}
        except Exception as e:
            r = {"command": command, "stdout": "", "stderr": str(e), "returncode": -1, "success": False}

        self.last_result = r
        return r

    def read_file(self, path: str, max_size_mb: int = 1) -> dict:
        """Liest eine Datei sicher aus der Sandbox."""
        if not self._is_safe_path(path):
            return {"success": False, "error": f"Access Denied: Path '{path}' is outside sandbox."}

        try:
            resolved = os.path.expanduser(path)
            if not os.path.isabs(resolved):
                resolved = os.path.join(self.working_dir, resolved)

            if not os.path.isfile(resolved):
                return {"success": False, "error": f"File not found: {path}"}

            size = os.path.getsize(resolved)
            if size > max_size_mb * 1024 * 1024:
                return {"success": False, "error": f"File too large ({size/1024/1024:.1f}MB). Max: {max_size_mb}MB"}

            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            return {"success": True, "content": content, "path": resolved, "size": size}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(self, path: str, content: str) -> dict:
        """Schreibt eine Datei sicher in die Sandbox."""
        if not self._is_safe_path(path):
            return {"success": False, "error": f"Access Denied: Path '{path}' is outside sandbox."}

        try:
            resolved = os.path.expanduser(path)
            if not os.path.isabs(resolved):
                resolved = os.path.join(self.working_dir, resolved)

            parent = os.path.dirname(resolved)
            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)

            return {"success": True, "path": resolved, "size": len(content)}
        except Exception as e:
            return {"success": False, "error": str(e)}
