--- architecture.md (updated) ---
# Moruk OS — Architecture
> Last updated: 2026-03-08 | Maintained by Firat Bulut

---

## Overview

```
┌─────────────────────────────────────────────────────┐
│                    UI Layer                         │
│   main_window.py  │  sidebar.py  │  settings_dialog │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  Core Layer                         │
│  brain.py  →  tool_router.py  →  executor.py        │
│  autonomy_loop.py  →  project_manager.py            │
│  deepthink.py  │  goal_engine.py  │  reflector.py   │
│  memory.py  │  vector_memory.py  │  context_router  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                 Plugin Layer                        │
│  plugins/*.py  →  plugin_manager.py (auto-discovery)│
│  list_tools │ scheduler │ vision │ multi_agent │ ... │
└─────────────────────────────────────────────────────┘
```

---

## UI Layer

### ui/main_window.py
- Haupt-Fenster der Anwendung (PyQt6)
- Initialisiert alle Core-Komponenten beim Start
- Startet Codebase-Index im Hintergrund-Thread
- DeepThink 🧠 Button (links vom Input)
- Project 🏗 Button (queued Autonomy-Projekt)
- Verbindet alle Signals/Slots zwischen Komponenten

### ui/sidebar.py
- Zeigt Tasks und Subtasks als Tree-Widget
- Jeder Task hat ✕ Delete-Button (rot on hover)
- Live-Updates während Autonomy läuft

### ui/settings_dialog.py
- Provider/Model Konfiguration
- Vision API separates Eingabefeld (URL + Key + Model)
- DeepThink Konfiguration
- Voice/Video Provider Slots

---

## Core Layer

### core/brain.py ⭐ (kritisch)
- Zentrale Denkmaschine — koordiniert alles
- `think()`: Tool-Loop mit max_iterations, depth, isolated, force_deepthink
- **NEW: core/tool_router.py (updated 2026-03-07)**
- Handles tool call extraction from AI responses using regex for <tool> and <tool_call> tags.
- Supports JSON and shorthand formats, sanitizes outputs, executes via Executor.
- Integrates with PluginManager, Memory, TaskManager, SelfModel.
- Recent fix: Restored UI compatibility with deepthink import.
- Lines: 227 | Complexity: 39 | Suggestions: Refactor for lower complexity, add type hints.

[Rest of the original content continues here...]