"""
Moruk AI OS - Plugin System
Auto-Discovery: .py Dateien in ~/moruk-os/plugins/ werden als Tools geladen.

Jedes Plugin muss enthalten:
- PLUGIN_NAME: str  (Tool-Name)
- PLUGIN_DESCRIPTION: str  (Beschreibung für System Prompt)
- PLUGIN_PARAMS: str  (Parameter-Doku für System Prompt)
- def execute(params: dict) -> dict  (Hauptfunktion, gibt {"success": bool, "result": str} zurück)

Optionale Felder:
- PLUGIN_VERSION: str
- PLUGIN_AUTHOR: str
- def on_load() -> None  (wird beim Laden aufgerufen)

Beispiel Plugin (plugins/hello.py):
    PLUGIN_NAME = "hello"
    PLUGIN_DESCRIPTION = "Says hello"
    PLUGIN_PARAMS = '"name": "string"'
    def execute(params):
        name = params.get("name", "World")
        return {"success": True, "result": f"Hello {name}!"}
"""

import sys
import importlib
import importlib.util
from pathlib import Path
from core.logger import get_logger

log = get_logger("plugins")

PLUGIN_DIR = Path(__file__).parent.parent / "plugins"


class PluginManager:
    """Lädt und verwaltet Plugins aus dem plugins/ Verzeichnis."""

    def __init__(self):
        self.plugins = {}  # name → module
        self._cached_prompt_docs = None
        self.load_all()

    def load_all(self):
        """Scannt plugins/ Verzeichnis und lädt alle .py Dateien."""
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        self.plugins = {}
        self._cached_prompt_docs = None

        for filepath in sorted(PLUGIN_DIR.glob("*.py")):
            if filepath.name.startswith("_"):
                continue
            try:
                self._load_plugin(filepath)
            except Exception as e:
                log.error(f"Failed to load plugin {filepath.name}: {e}")

        if self.plugins:
            log.info(f"Loaded {len(self.plugins)} plugins: {list(self.plugins.keys())}")

    def _load_plugin(self, filepath: Path):
        """Lädt ein einzelnes Plugin."""
        module_name = f"plugin_{filepath.stem}"

        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if not spec or not spec.loader:
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Pflichtfelder prüfen
        name = getattr(module, "PLUGIN_NAME", None)
        if not name:
            log.warning(f"Plugin {filepath.name}: Missing PLUGIN_NAME, skipping")
            return

        if not hasattr(module, "execute"):
            log.warning(f"Plugin {filepath.name}: Missing execute() function, skipping")
            return

        self.plugins[name] = module
        log.info(f"Plugin loaded: '{name}' from {filepath.name}")

        # Optional: on_load callback
        if hasattr(module, "on_load"):
            try:
                module.on_load()
            except Exception as e:
                log.warning(f"Plugin '{name}' on_load error: {e}")

    def reload_all(self):
        """Lädt alle Plugins neu (Hot-Reload)."""
        old_count = len(self.plugins)
        self.plugins = {}
        self._cached_prompt_docs = None

        # Module aus sys.modules entfernen, um frischen Import zu erzwingen
        for key in list(sys.modules.keys()):
            if key.startswith("plugin_"):
                del sys.modules[key]

        self.load_all()
        self._cached_prompt_docs = None
        log.info(f"Plugins reloaded. {old_count} -> {len(self.plugins)}")

    def execute(self, name: str, params: dict) -> dict:
        """Führt ein Plugin aus."""
        if name not in self.plugins:
            return {"tool": name, "success": False, "result": f"Plugin {name} not found"}

        try:
            result = self.plugins[name].execute(params)
            if not isinstance(result, dict) or "success" not in result or "result" not in result:
                log.warning(f"Plugin {name} returned invalid format. Expected dict with 'success' and 'result'")
                return {"tool": name, "success": True, "result": str(result)}

            result["tool"] = name
            return result
        except Exception as e:
            return {"tool": name, "success": False, "result": f"Plugin error: {str(e)}"}

    def has_plugin(self, name: str) -> bool:
        return name in self.plugins

    def get_names(self) -> list:
        return list(self.plugins.keys())

    def get_prompt_docs(self) -> str:
        """
        Generiert Tool-Dokumentation für den System Prompt.
        Nur PLUGIN_CORE = True Plugins werden in jeden Prompt injiziert.
        Nicht-Core Plugins sind via list_tools abrufbar.
        Cache wird nach reload_all() invalidiert.
        """
        if not self.plugins:
            return ""

        if self._cached_prompt_docs is not None:
            return self._cached_prompt_docs

        # Nur PLUGIN_CORE = True Plugins
        core_plugins = {
            name: module for name, module in self.plugins.items()
            if getattr(module, "PLUGIN_CORE", False)
        }

        if not core_plugins:
            # Fallback: alle anzeigen wenn keiner PLUGIN_CORE gesetzt hat
            core_plugins = self.plugins

        non_core = [n for n, m in self.plugins.items() if not getattr(m, "PLUGIN_CORE", False)]

        docs = ["\n--- CORE TOOLS (always available) ---"]
        for name, module in core_plugins.items():
            desc = getattr(module, "PLUGIN_DESCRIPTION", "No description")
            # Beschreibung auf ersten Satz kürzen
            desc = desc.split(".")[0].split("\n")[0][:100]
            params_doc = getattr(module, "PLUGIN_PARAMS", "")
            docs.append(f'\n{name}: {desc}')
            if params_doc:
                docs.append(f'  Parameters: {{{params_doc}}}')

        if non_core:
            docs.append(f'\n[{len(non_core)} weitere Tools via list_tools: {", ".join(non_core[:8])}{"..." if len(non_core) > 8 else ""}]')

        self._cached_prompt_docs = "\n".join(docs)
        return self._cached_prompt_docs

    def invalidate_cache(self):
        """Cache invalidieren — nach reload oder neuem Plugin aufrufen."""
        self._cached_prompt_docs = None
