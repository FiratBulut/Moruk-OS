"""
Moruk AI OS - Plugin System
Auto-Discovery: .py Dateien in plugins/ werden als Tools geladen.

Jedes Plugin muss enthalten:
- PLUGIN_NAME: str  (Tool-Name)
- PLUGIN_DESCRIPTION: str  (Beschreibung für System Prompt)
- PLUGIN_PARAMS: str  (Parameter-Doku für System Prompt)
- def execute(params: dict) -> dict  (Hauptfunktion, gibt {"success": bool, "result": str} zurück)

Optionale Felder:
- PLUGIN_VERSION: str
- PLUGIN_AUTHOR: str
- def on_load() -> None  (wird beim Laden aufgerufen)
- def on_unload() -> None (wird beim Hot-Reloading vor dem Zerstören aufgerufen)
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

        # Fügt den Plugin-Ordner zum PYTHONPATH hinzu, damit Plugins
        # relative/lokale Hilfsdateien importieren können.
        if str(PLUGIN_DIR) not in sys.path:
            sys.path.append(str(PLUGIN_DIR))

        self.load_all()

    def load_all(self):
        """Scannt plugins/ Verzeichnis und lädt alle .py Dateien."""
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        loaded_count = 0

        for file_path in PLUGIN_DIR.glob("*.py"):
            # Versteckte Dateien und Init-Dateien überspringen
            if file_path.name.startswith("_"):
                continue

            module_name = f"plugins.{file_path.stem}"

            try:
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if not spec or not spec.loader:
                    continue

                module = importlib.util.module_from_spec(spec)
                # WICHTIG: Sofort in sys.modules registrieren, falls es andere Dinge importiert
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                plugin_name = getattr(module, "PLUGIN_NAME", None)
                if not plugin_name:
                    # Kein valides Plugin (z.B. nur eine Helper-Datei) -> ignorieren
                    sys.modules.pop(module_name, None)
                    continue

                # Sicherheitscheck: Hat das Plugin eine execute-Methode?
                if not hasattr(module, "execute"):
                    log.warning(
                        f"Plugin '{plugin_name}' abgelehnt: Keine execute() Methode gefunden!"
                    )
                    sys.modules.pop(module_name, None)
                    continue

                # Optionaler Initialisierungs-Hook
                if hasattr(module, "on_load"):
                    try:
                        module.on_load()
                    except Exception as e:
                        log.error(f"Error in on_load of plugin '{plugin_name}': {e}")

                self.plugins[plugin_name] = module
                loaded_count += 1

            except Exception as e:
                log.error(f"Failed to load plugin {file_path.name}: {e}")
                # Aufräumen, falls der Load mittendrin gecrasht ist
                sys.modules.pop(module_name, None)

        if loaded_count > 0:
            log.info(f"{loaded_count} Plugins erfolgreich geladen.")

    def reload_all(self):
        """Entlädt alle aktiven Plugins sicher und lädt sie neu von der Festplatte."""
        # 1. Clean Shutdown für aktive Plugins (Ressourcenfreigabe)
        for name, module in self.plugins.items():
            if hasattr(module, "on_unload"):
                try:
                    module.on_unload()
                except Exception as e:
                    log.warning(f"Error in on_unload of plugin '{name}': {e}")

            # 2. FIX: Den WAHREN Python-Modulnamen aus dem Cache löschen!
            mod_name = getattr(module, "__name__", f"plugins.{name}")
            sys.modules.pop(mod_name, None)

        self.plugins.clear()
        self._cached_prompt_docs = None

        # 3. Frischer Neustart
        self.load_all()
        log.info("Alle Plugins wurden neu geladen (Hot-Reload).")

    def has_plugin(self, name: str) -> bool:
        return name in self.plugins

    def execute(self, name: str, params: dict) -> dict:
        """Führt ein Plugin aus. Fängt alle Abstürze im Plugin ab."""
        if name not in self.plugins:
            return {"success": False, "result": f"Plugin {name} not found"}

        try:
            return self.plugins[name].execute(params)
        except Exception as e:
            log.error(f"Plugin '{name}' crashed during execution: {e}")
            return {"success": False, "result": f"Plugin internal error: {e}"}

    def get_prompt_docs(self) -> str:
        """
        Generiert die Tool-Dokumentation für den LLM-System-Prompt.
        Wird nach dem ersten Aufruf gecached.
        """
        if not self.plugins:
            return ""

        if self._cached_prompt_docs is not None:
            return self._cached_prompt_docs

        # Finde Core Plugins (oft genutzte Standard-Tools)
        core_plugins = {
            name: module
            for name, module in self.plugins.items()
            if getattr(module, "PLUGIN_CORE", False)
        }

        # Fallback: Wenn niemand Core ist, zeige alle an
        if not core_plugins:
            core_plugins = self.plugins

        non_core = [
            n for n, m in self.plugins.items() if not getattr(m, "PLUGIN_CORE", False)
        ]

        docs = ["\n--- CORE TOOLS (always available) ---"]
        for name, module in core_plugins.items():
            desc = getattr(module, "PLUGIN_DESCRIPTION", "No description")
            # Beschreibung auf den ersten Satz kürzen (Token-Optimierung)
            desc = desc.split(".")[0].split("\n")[0][:100]
            params_doc = getattr(module, "PLUGIN_PARAMS", "")

            docs.append(f"\n{name}: {desc}")
            if params_doc:
                docs.append(f"  Parameters: {{{params_doc}}}")

        if non_core:
            # Zeigt dem LLM, dass es noch mehr Tools gibt (falls 'list_tools' existiert)
            docs.append(
                f'\n[{len(non_core)} weitere Tools via list_tools: {", ".join(non_core[:8])}{"..." if len(non_core) > 8 else ""}]'
            )

        self._cached_prompt_docs = "\n".join(docs)
        return self._cached_prompt_docs

    def invalidate_cache(self):
        self._cached_prompt_docs = None
