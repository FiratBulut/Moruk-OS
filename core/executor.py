"""
Moruk AI OS - Executor
Terminal-Befehle und File-Operationen. (Gehärtet & Modular)
"""

import subprocess
import os
import threading
from pathlib import Path


class Executor:
    """Führt System-Befehle und File-Ops für Moruk OS aus."""

    def __init__(self, working_dir: str = None, strict_sandbox: bool = False):
        self.working_dir = working_dir or str(Path(__file__).parent.parent.resolve())
        self.strict_sandbox = (
            strict_sandbox  # True = Darf den Moruk-Ordner nicht verlassen
        )
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

        self.env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    def _resolve_path(self, path: str) -> Path | None:
        """
        Löst Pfade sicher auf (expandiert '~', macht Pfade absolut).
        Gibt None zurück, wenn die Sandbox-Regeln verletzt werden.
        """
        try:
            target_path = Path(path).expanduser()
            if not target_path.is_absolute():
                target_path = Path(self.working_dir) / target_path

            target_path = target_path.resolve()

            # Wenn Sandbox aktiv, blockiere Zugriffe außerhalb des working_dir
            if self.strict_sandbox:
                working_dir_path = Path(self.working_dir).resolve()
                if not target_path.is_relative_to(working_dir_path):
                    return None

            return target_path
        except Exception:
            return None

    def run_command(self, command: str, timeout: int = 60) -> dict:
        """Führt einen Bash-Befehl aus (Unterstützt Pipes & Umleitungen sicher via bash -c)."""
        if not command.strip():
            return {"success": False, "error": "Empty command"}

        try:
            # Wir nutzen "bash -c", um KI-Befehle mit Pipes (|) und redirects (>) zu erlauben.
            # shell=False bleibt für die Sicherheit des Subprozesses erhalten.
            args = ["bash", "-c", command]

            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_dir,
                env=self.env,
            )
            r = {
                "command": command,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            r = {
                "command": command,
                "stdout": "",
                "stderr": f"Timeout after {timeout}s",
                "returncode": -1,
                "success": False,
            }
        except Exception as e:
            r = {
                "command": command,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
                "success": False,
            }

        self.last_result = r
        return r

    def read_file(self, path: str, max_size_mb: int = 2) -> dict:
        """Liest eine Datei sicher aus."""
        resolved = self._resolve_path(path)
        if not resolved:
            return {
                "success": False,
                "error": f"Access Denied: Path '{path}' is outside sandbox.",
            }

        try:
            if not resolved.is_file():
                return {"success": False, "error": f"File not found: {resolved}"}

            size = resolved.stat().st_size
            if size > max_size_mb * 1024 * 1024:
                return {
                    "success": False,
                    "error": f"File too large ({size/1024/1024:.1f}MB). Max: {max_size_mb}MB",
                }

            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            return {
                "success": True,
                "content": content,
                "path": str(resolved),
                "size": size,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(self, path: str, content: str) -> dict:
        """Schreibt eine Datei sicher und erstellt fehlende Ordner."""
        resolved = self._resolve_path(path)
        if not resolved:
            return {
                "success": False,
                "error": f"Access Denied: Path '{path}' is outside sandbox.",
            }

        try:
            # Erstelle übergeordnete Ordner, falls sie nicht existieren
            resolved.parent.mkdir(parents=True, exist_ok=True)

            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)

            return {"success": True, "path": str(resolved), "size": len(content)}
        except Exception as e:
            return {"success": False, "error": str(e)}
