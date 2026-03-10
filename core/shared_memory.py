"""
Moruk OS — Shared Memory Plugin v2
Thread-safe key-value storage for multi-agent coordination.

v2 Änderungen:
- Thread-safe mit RLock (wichtig für parallele Agenten)
- Neue Actions: get_all, clear
- Atomic write bleibt
"""

import json
import os
import threading
from pathlib import Path

PLUGIN_NAME = "shared_memory"
PLUGIN_DESCRIPTION = (
    "Thread-safe shared key-value storage for multi-agent coordination. "
    "Actions: store, get, list, get_all, delete, clear."
)
PLUGIN_PARAMS = {
    "action": "store|get|list|get_all|delete|clear",
    "key": "storage key",
    "value": "value to store (for store action)",
}
PLUGIN_CORE = False

STORAGE_PATH = Path(__file__).parent.parent / "data" / "shared_memory_storage.json"
_lock = threading.RLock()


def _load() -> dict:
    try:
        if STORAGE_PATH.exists():
            with open(STORAGE_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save(data: dict):
    STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORAGE_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STORAGE_PATH)


def execute(params: dict) -> dict:
    action = params.get("action", "")
    key = params.get("key", "")
    value = params.get("value", "")

    try:
        with _lock:
            data = _load()

            if action == "store":
                if not key:
                    return {"success": False, "result": "Missing key"}
                data[key] = value
                _save(data)
                return {"success": True, "result": f"✅ Stored '{key}'"}

            elif action == "get":
                if key not in data:
                    return {"success": False, "result": f"❌ Key '{key}' not found"}
                return {"success": True, "result": data[key]}

            elif action == "list":
                return {"success": True, "result": list(data.keys())}

            elif action == "get_all":
                return {"success": True, "result": data}

            elif action == "delete":
                if key not in data:
                    return {"success": False, "result": f"❌ Key '{key}' not found"}
                del data[key]
                _save(data)
                return {"success": True, "result": f"🗑️ Deleted '{key}'"}

            elif action == "clear":
                data.clear()
                _save(data)
                return {"success": True, "result": "🗑️ All entries cleared"}

            else:
                return {
                    "success": False,
                    "result": f"❌ Invalid action '{action}'. Use: store, get, list, get_all, delete, clear",
                }

    except Exception as e:
        return {"success": False, "result": f"Error: {e}"}
