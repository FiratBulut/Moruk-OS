"""
Moruk OS - List Tools Plugin
Zeigt dem Agent alle verfügbaren Tools/Plugins an.
PLUGIN_CORE = True → immer im System Prompt sichtbar
"""

PLUGIN_NAME = "list_tools"
PLUGIN_DESCRIPTION = "Lists ALL available tools and plugins with descriptions. Call this when you're unsure what you can do."
PLUGIN_PARAMS = '"filter": "optional: core, extra, or leave empty for all"'
PLUGIN_CORE = True  # Immer sichtbar — Agent soll wissen dass er dieses Tool hat

# Wird beim Execute mit dem PluginManager verbunden (von ToolRouter gesetzt)
_plugin_manager = None


def execute(params: dict) -> dict:
    filter_type = params.get("filter", "all").lower()

    builtin_tools = """BUILT-IN TOOLS (always available):
  terminal       — Shell-Befehle ausführen
  read_file      — Datei lesen
  write_file     — Datei schreiben/erstellen (mit Auto-Syntax-Check + Rollback für .py)
  self_edit      — Datei chirurgisch editieren
  task_create    — Neue Aufgabe erstellen
  task_complete  — Aufgabe als erledigt markieren
  task_fail      — Aufgabe als fehlgeschlagen markieren
  memory_store   — In Langzeitgedächtnis speichern
  memory_search  — Langzeitgedächtnis durchsuchen
  start_project  — Neues autonomes Projekt starten
"""

    if _plugin_manager is None:
        return {
            "success": True,
            "result": builtin_tools
            + "\n(Plugin-Liste nicht verfügbar — PluginManager nicht verbunden)",
        }

    # Alle Plugins mit PLUGIN_CORE Status auflisten
    lines = ["\nPLUGINS:"]
    for name, module in _plugin_manager.plugins.items():
        is_core = getattr(module, "PLUGIN_CORE", False)
        desc = getattr(module, "PLUGIN_DESCRIPTION", "")
        desc = desc.split(".")[0].split("\n")[0][:80]
        tag = "[CORE]" if is_core else "[extra]"

        if filter_type == "core" and not is_core:
            continue
        if filter_type == "extra" and is_core:
            continue

        lines.append(f"  {tag} {name}: {desc}")

    plugin_list = "\n".join(lines)

    return {"success": True, "result": builtin_tools + plugin_list}
