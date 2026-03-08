"""
Moruk AI OS - Brain Module v2
Provider-agnostischer LLM Abstraction Layer mit Tool-Loop.
"""

import os
import time
import re
import json
import base64
from datetime import datetime
from pathlib import Path


CONFIG_DIR = Path(__file__).parent.parent / "config"
DATA_DIR = Path(__file__).parent.parent / "data"


class Brain:
    """Provider-agnostisches LLM Interface mit Tool-Execution-Loop."""

    def __init__(self):
        from core.logger import get_logger
        self.log = get_logger("brain")

        self.settings = self._load_settings()
        self.system_prompt = self._load_system_prompt()
        self.conversation_history = self._load_conversation()
        self.client = None
        self._provider_type = "openai_compatible"  # "anthropic" oder "openai_compatible"
        self.tool_router = None  # Wird von MainWindow gesetzt
        self.deepthink = None    # Wird von MainWindow gesetzt
        self.last_token_usage = {}  # Token tracking
        self._init_client()
        self._init_deepthink()
        self.log.info(f"Brain initialized. Provider: {self.settings.get('provider')}, configured: {self.is_configured()}")

    # ── Settings ──────────────────────────────────────────────

    def _load_settings(self) -> dict:
        """Lädt Settings. Prüft zuerst user_settings.json (wird nie überschrieben)."""
        user_path = CONFIG_DIR / "user_settings.json"
        settings_path = CONFIG_DIR / "settings.json"

        defaults = {"provider": "anthropic", "api_key": "", "model": "", "max_tokens": 4096, "temperature": 0.7}
        if settings_path.exists():
            try:
                with open(settings_path, "r") as f:
                    defaults = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        if user_path.exists():
            try:
                with open(user_path, "r") as f:
                    user = json.load(f)
                defaults.update(user)
            except (json.JSONDecodeError, IOError):
                pass

        return defaults

    def configure(self, settings: dict):
        """Alias für save_settings() — wird von agent_runner.py aufgerufen."""
        self.save_settings(settings)

    @classmethod
    def get_provider_info(cls) -> dict:
        """Gibt alle bekannten Provider mit Base-URLs zurück (für Settings Dialog)."""
        info = {
            "anthropic": {"base_url": "", "note": "Eigenes SDK"},
            "openai":    {"base_url": "https://api.openai.com/v1", "note": ""},
            "ollama":    {"base_url": "http://localhost:11434/v1", "note": "Lokal"},
        }
        for name, url in cls.PROVIDER_BASE_URLS.items():
            if name not in info:
                info[name] = {"base_url": url, "note": "OpenAI-kompatibel"}
        return info

    def save_settings(self, settings: dict):
        """Speichert Settings in BEIDE Dateien (default + user-persistent)."""
        self.settings = settings
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        settings_path = CONFIG_DIR / "settings.json"
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)

        # User-Settings separat speichern (überlebt Updates!)
        user_path = CONFIG_DIR / "user_settings.json"
        # FIX: Sync api_key in active_model_config before saving
        if settings.get("api_key") and "active_model_config" in settings:
            if not settings["active_model_config"].get("api_key"):
                settings["active_model_config"]["api_key"] = settings["api_key"]

        user_data = {
            "provider": settings.get("provider", ""),
            "api_key": settings.get("api_key", ""),
            "base_url": settings.get("base_url", ""),
            "model": settings.get("model", ""),
            "max_tokens": settings.get("max_tokens", 4096),
            "temperature": settings.get("temperature", 0.7),
            "providers": settings.get("providers", {}),
            "active_model_config": settings.get("active_model_config", {}),
            # DeepThink Settings
            "deepthink_provider": settings.get("deepthink_provider", ""),
            "deepthink_api_key": settings.get("deepthink_api_key", ""),
            "deepthink_model": settings.get("deepthink_model", ""),
            "deepthink_base_url": settings.get("deepthink_base_url", ""),
        }
        with open(user_path, "w") as f:
            json.dump(user_data, f, indent=2)

        self._init_client()
        self._init_deepthink()

    def _load_system_prompt(self) -> str:
        prompt_path = CONFIG_DIR / "system_prompt.txt"
        if prompt_path.exists():
            with open(prompt_path, "r") as f:
                return f.read()
        return "You are Moruk OS, an autonomous AI operating system."

    # ── Conversation Persistence ──────────────────────────────

    def _load_conversation(self) -> list:
        conv_path = DATA_DIR / "conversation.json"
        if conv_path.exists():
            try:
                with open(conv_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save_conversation(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conv_path = DATA_DIR / "conversation.json"
        tmp_path = conv_path.with_suffix(".tmp")
        save_data = self.conversation_history[-50:]
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, conv_path)
        except Exception as e:
            self.log.error(f"Conversation save failed: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def clear_conversation(self):
        self.conversation_history = []
        self._save_conversation()

    # ── Client Initialization ─────────────────────────────────

    # Bekannte Provider → OpenAI-kompatible Base-URLs
    PROVIDER_BASE_URLS = {
        "google":     "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/",
        "mistral":    "https://api.mistral.ai/v1",
        "groq":       "https://api.groq.com/openai/v1",
        "together":   "https://api.together.xyz/v1",
        "deepseek":   "https://api.deepseek.com/v1",
        "kimi":       "https://api.moonshot.cn/v1",
        "moonshot":   "https://api.moonshot.cn/v1",
        "minimax":    "https://api.minimax.chat/v1",
        "xai":        "https://api.x.ai/v1",
        "grok":       "https://api.x.ai/v1",
        "cohere":     "https://api.cohere.ai/compatibility/v1",
        "perplexity": "https://api.perplexity.ai",
        "cerebras":   "https://api.cerebras.ai/v1",
    }

    def _init_client(self):
        provider = self.settings.get("provider", "anthropic")
        api_key = self.settings.get("api_key", "")

        model_config = self.settings.get("active_model_config", {})
        if model_config.get("api_key"):
            api_key = model_config["api_key"]
        model_base_url = model_config.get("base_url", "")
        self._provider_type = "openai_compatible"

        if not api_key:
            self.client = None
            return

        try:
            if provider == "anthropic":
                from anthropic import Anthropic
                self.client = Anthropic(api_key=api_key)
                self._provider_type = "anthropic"

            elif provider == "ollama":
                from openai import OpenAI
                base_url = (model_base_url
                            or self.settings.get("providers", {}).get("ollama", {}).get("base_url", "")
                            or "http://localhost:11434")
                if not base_url.endswith("/v1"):
                    base_url = base_url.rstrip("/") + "/v1"
                self.client = OpenAI(base_url=base_url, api_key="ollama")

            elif provider in self.PROVIDER_BASE_URLS:
                from openai import OpenAI
                base_url = model_base_url or self.PROVIDER_BASE_URLS[provider]
                self.client = OpenAI(base_url=base_url, api_key=api_key)

            elif provider == "openai":
                from openai import OpenAI
                self.client = (OpenAI(base_url=model_base_url, api_key=api_key)
                               if model_base_url else OpenAI(api_key=api_key))

            else:
                # Custom oder unbekannter Provider → OpenAI-kompatibel
                from openai import OpenAI
                base_url = (model_base_url
                            or self.settings.get("providers", {}).get(provider, {}).get("base_url", "")
                            or self.settings.get("providers", {}).get("custom", {}).get("base_url", ""))
                if base_url:
                    self.client = OpenAI(base_url=base_url, api_key=api_key)
                else:
                    self.client = None
                    self.log.warning(f"Provider '{provider}': kein base_url. In Settings eintragen.")

            if self.client:
                effective_url = model_base_url or self.PROVIDER_BASE_URLS.get(provider, "default")
                self.log.info(f"Client ready: provider={provider} ({self._provider_type}), "
                              f"model={self.settings.get('model')}, base_url={effective_url}")
        except ImportError:
            self.log.error("openai package fehlt. Bitte: pip install openai")
            self.client = None
        except Exception as e:
            self.log.error(f"Client init error: {e}")
            self.client = None

    def is_configured(self) -> bool:
        if self.client is None:
            return False
        api_key = self.settings.get("api_key", "")
        model_key = self.settings.get("active_model_config", {}).get("api_key", "")
        return bool(api_key or model_key)

    def _init_deepthink(self):
        """Initialisiert DeepThink wenn konfiguriert."""
        try:
            from core.deepthink import DeepThink
            self.deepthink = DeepThink()
            self.deepthink.configure(self.settings)
            if self.deepthink.is_enabled():
                self.log.info(f"DeepThink enabled: {self.settings.get('deepthink_model')}")
        except Exception as e:
            self.log.error(f"DeepThink init failed: {e}")
            self.deepthink = None

    # ── Core Thinking with Tool Loop ──────────────────────────

    MINIMAL_PROMPT = (
        "You are Moruk OS, an AI assistant. Be direct and concise. "
        "Respond naturally in the user's language."
    )

    # Wird zu JEDEM System-Prompt hinzugefügt — verhindert native function calling
    TOOL_FORMAT_BLOCK = """
CRITICAL - TOOL USAGE FORMAT:
You MUST use this EXACT XML format for ALL tool calls. NO exceptions.
Do NOT use native function calling, JSON function arrays, or any other format.

<tool_call>{"tool": "tool_name", "params": {"key": "value"}}</tool_call>

Examples:
<tool_call>{"tool": "terminal", "params": {"command": "ls -la"}}</tool_call>
<tool_call>{"tool": "task_create", "params": {"title": "My task", "priority": "normal"}}</tool_call>
<tool_call>{"tool": "task_complete", "params": {"task_id": "abc123"}}</tool_call>

NEVER use: function_call, tool_choice, JSON arrays, or any non-XML format.
ALWAYS use: <tool_call>{...}</tool_call> XML tags exactly as shown above.
"""

    def think(self, user_message: str, extra_context: str = "",
              on_tool_start=None, on_tool_result=None, max_iterations: int = 10,
              depth: int = 3, on_token=None, isolated: bool = False,
              force_deepthink: bool = False) -> str:
        """
        Haupt-Denkfunktion mit Tool-Execution-Loop.
        depth: 1=minimal, 2=question, 3=task, 4=dev, 5=autonomous
        on_token: Callback für Streaming (wird mit jedem Token aufgerufen)
        isolated: True = eigene History (für autonome Tasks, kein Chat-Kontext)
        """
        if not self.is_configured():
            return "[MORUK OS] Kein Provider konfiguriert. Öffne Settings (⚙️) und gib API Key + Model ein."

        # DeepThink Force Mode: Button im UI aktiviert
        if force_deepthink and self.deepthink and self.deepthink.is_enabled():
            self.conversation_history.append({"role": "user", "content": user_message})
            deep_response = self.deepthink.think(
                user_message, extra_context=extra_context,
                conversation=self.conversation_history[-20:],
                on_token=on_token
            )
            if deep_response:
                self.conversation_history.append({"role": "assistant", "content": deep_response})
                self._save_conversation()
                return f"🧠 {deep_response}"
            # Fallback auf Small Model wenn DeepThink leer
        
        # DeepThink Direct Mode: User hat explizit "think deep" gesagt
        if self.deepthink and self.deepthink.should_think_deep(user_message):
            self.conversation_history.append({"role": "user", "content": user_message})
            deep_response = self.deepthink.think(
                user_message, extra_context=extra_context,
                conversation=self.conversation_history[-20:],
                on_token=on_token
            )
            if deep_response:
                self.conversation_history.append({"role": "assistant", "content": deep_response})
                self._save_conversation()
                return f"🧠 {deep_response}"

        # System prompt basierend auf Depth
        if depth <= 1:
            system = self.MINIMAL_PROMPT
        elif depth <= 2:
            system = self.MINIMAL_PROMPT + "\n\nYou can use tools if needed."
            if extra_context:
                system += f"\n\n{extra_context}"
        else:
            system = self.system_prompt
            if extra_context:
                system += f"\n\n--- CURRENT CONTEXT ---\n{extra_context}"

        # Tool-Format Block bei depth >= 2 (wenn Tools gebraucht werden)
        # Verhindert native function calling bei Gemini/anderen Providern
        if depth >= 2 and self.tool_router:
            system += self.TOOL_FORMAT_BLOCK

        # Vision-Info hinzufügen wenn Model Vision hat
        if self.has_vision() and "[Attached image:" in user_message:
            system += "\n\n--- CAPABILITIES ---"
            system += "\nYou have VISION enabled. When the user attaches an image, you can see it directly."
            system += "\nDo NOT try to install PIL/Pillow or any image library. You receive images via the API."
            system += "\nDescribe what you see in the image directly."

        # Plugin-Docs hinzufügen wenn Plugins geladen
        if self.tool_router and hasattr(self.tool_router, 'plugin_manager'):
            plugin_docs = self.tool_router.plugin_manager.get_prompt_docs()
            if plugin_docs:
                # Plugin Docs kürzen wenn zu lang (max 3000 Zeichen)
                if len(plugin_docs) > 3000:
                    plugin_docs = plugin_docs[:3000] + "\n... [weitere Plugins verfügbar]"
                system += plugin_docs

        # Self-Awareness injizieren
        if depth >= 4 and self.tool_router and hasattr(self.tool_router, 'self_model'):
            self_ctx = self.tool_router.self_model.get_self_awareness_context()
            if self_ctx:
                system += "\n\n--- SELF-AWARENESS ---\n" + self_ctx

        self.log.info(f"Think: depth={depth}, system_prompt_len={len(system.split())} words, "
                      f"max_iter={max_iterations}")

        # Isolierte History für autonome Tasks — kein Chat-Kontext
        if isolated:
            active_history = []
        else:
            active_history = self.conversation_history
        active_history.append({"role": "user", "content": user_message})

        try:
            full_response = ""
            iteration = 0
            self.log.info(f"Think start: '{user_message[:80]}' (isolated={isolated}, iterations max: {max_iterations})")

            while iteration < max_iterations:
                iteration += 1

                # Streaming: an wenn on_token gesetzt und keine Tool-Calls in dieser Iteration erwartet.
                # Iteration > 1 bedeutet wir sind bereits im Tool-Loop — da ist Streaming sicher.
                # depth <= 2 (smalltalk/frage): Tool-Loop unwahrscheinlich → direkt streamen.
                # depth >= 3, iteration == 1: erst non-streaming, Tool-Call-Check, dann ggf. stream.
                use_stream = on_token is not None and (depth <= 2 or iteration > 1)

                # History trimmen: max 20 Messages für Chat, 10 für autonome Tasks
                history_limit = 10 if isolated else 20
                trimmed_history = active_history[-history_limit:] if len(active_history) > history_limit else active_history

                if use_stream:
                    response_text = self._call_provider_stream(system, on_token=on_token, history=trimmed_history)
                else:
                    response_text = self._call_provider(system, history=trimmed_history)

                # Tool Calls prüfen und ausführen
                # Tool Calls prüfen und ausführen
                if self.tool_router and self.tool_router.has_tool_calls(response_text):
                    full_response += self._strip_tool_calls(response_text) + "\n"
                    calls = self.tool_router.extract_tool_calls(response_text)
                    results = []
                    
                    for call in calls:
                        tool_name = call.get("tool", "unknown")
                        params = call.get("params", {})

                        # ── SICHERHEITS-LAYER (3 Stufen) ──────────────────────

                        # Stufe 1: Lokaler Shield (kein API Call) — schnell
                        # Nur für risikoreiche Tools
                        RISKY_TOOLS = {"terminal", "write_file", "self_edit", "system_repair"}
                        if tool_name in RISKY_TOOLS and self.deepthink and self.deepthink.is_enabled():
                            shield = self.deepthink.review_tool_call(tool_name, params, user_message)
                            if not shield.get("approved", True):
                                reason = shield.get("reason", "Unbekannt")
                                self.log.warning(f"🛡 Shield blockiert {tool_name}: {reason}")
                                results.append({
                                    "tool": tool_name, "success": False,
                                    "result": f"Shield: {reason}"
                                })
                                continue

                        # Stufe 2: Syntax-Check für Python-Dateien vor dem Schreiben
                        if tool_name in ("write_file", "self_edit"):
                            path = params.get("path", "")
                            content_to_write = params.get("content", "")
                            if path.endswith(".py") and content_to_write:
                                import ast as _ast
                                try:
                                    _ast.parse(content_to_write)
                                    self.log.info(f"✅ Syntax OK: {path}")
                                except SyntaxError as se:
                                    self.log.warning(f"❌ Syntax-Fehler in {path}: {se}")
                                    results.append({
                                        "tool": tool_name, "success": False,
                                        "result": f"Syntax-Fehler verhindert Schreiben: {se}. Bitte korrigiere den Code."
                                    })
                                    continue

                        # Stufe 3: DeepThink validate_action (API Call) — nur wirklich gefährliche Befehle
                        _needs_audit = False
                        if tool_name in RISKY_TOOLS and self.deepthink and self.deepthink.is_enabled():
                            if tool_name == "terminal":
                                # Nur bei destruktiven Befehlen — nicht bei ls, cat, grep etc.
                                cmd = params.get("command", "").strip().lower()
                                DESTRUCTIVE = ("rm ", "rm	", "rmdir", "mv ", "dd ", "mkfs",
                                               "> /", "chmod 777", "shred", "truncate", "pkill", "kill ")
                                _needs_audit = any(cmd.startswith(d) or f" {d}" in cmd for d in DESTRUCTIVE)
                            else:
                                # write_file, self_edit: immer auditieren
                                _needs_audit = True

                        if _needs_audit:
                            self.log.info(f"[DeepThink] Audit: {tool_name}")
                            is_safe = self.deepthink.validate_action(tool_name, params, user_message)
                            if not is_safe:
                                self.log.warning(f"🚨 DeepThink hat {tool_name} gestoppt!")
                                results.append({
                                    "tool": tool_name, "success": False,
                                    "result": f"DeepThink Audit: Aktion '{tool_name}' blockiert."
                                })
                                continue

                        # Stufe 4: Rollback-Backup vor Datei-Schreiboperationen
                        if tool_name in ("write_file", "self_edit"):
                            import shutil as _shutil
                            path = params.get("path", "")
                            if path:
                                _path = Path(path).expanduser()
                                if _path.exists():
                                    backup = _path.with_suffix(_path.suffix + ".bak")
                                    try:
                                        _shutil.copy2(_path, backup)
                                        self.log.info(f"💾 Rollback-Backup: {backup}")
                                    except Exception as _e:
                                        self.log.warning(f"Backup fehlgeschlagen: {_e}")

                        # ── Tool ausführen ─────────────────────────────────────
                        if on_tool_start:
                            on_tool_start(tool_name, params)

                        result = self.tool_router.execute_tool(call)
                        results.append(result)

                        if on_tool_result:
                            on_tool_result(tool_name, result)

                        # task_complete/task_fail → Loop sofort beenden
                        if tool_name in ("task_complete", "complete_task", "task_fail", "fail_task"):
                            full_response = result.get("result", "Task abgeschlossen.")
                            break
                    
                    # ... Rest wie gehabt (results_text, history update)

                    results_text = self.tool_router.format_results(results)

                    active_history.append({"role": "assistant", "content": response_text})
                    # Tool Results in History auf 2000 Zeichen kürzen
                    results_truncated = results_text[:2000] + "..." if len(results_text) > 2000 else results_text
                    active_history.append({
                        "role": "user",
                        "content": f"[SYSTEM] Tool execution results:\n{results_truncated}\n\nIf the task is complete, respond with your final answer. If more steps are needed, continue."
                    })

                else:
                    # Keine Tool Calls → Finale Antwort
                    if response_text:
                        full_response += response_text
                    elif not full_response:
                        # Leer-Antwort vom Model — max 1 Retry pro Loop
                        self.log.warning(f"Empty response from model on iteration {iteration}, retrying once...")
                        if iteration < max_iterations:
                            active_history.append({   # active_history! nicht self.conversation_history
                                "role": "user",
                                "content": "[SYSTEM] Your previous response was empty. Please respond now."
                            })
                            continue
                        else:
                            full_response = "[Moruk OS] Keine Antwort vom Modell erhalten. Bitte nochmal versuchen."

                    # DeepThink Review (wenn konfiguriert + relevant)
                    # DeepThink Review: nur bei depth 5 (autonomous) oder force_deepthink
                    # Bei depth 3/4 kein Review — verhindert Doppel-Ausführung
                    _dt_should = depth >= 5 or force_deepthink
                    if (self.deepthink and self.deepthink.is_enabled()
                            and _dt_should
                            and self.deepthink.should_review(user_message, full_response, depth)):
                        review = self.deepthink.review(user_message, full_response)
                        verdict = review.get("verdict", "approve")

                        if verdict == "revise" and review.get("suggestion"):
                            self.log.info(f"DeepThink: revise — {review['suggestion'][:100]}")
                            active_history.append({"role": "assistant", "content": full_response})
                            active_history.append({
                                "role": "user",
                                "content": f"[SYSTEM] Supervisor review: REVISE.\n"
                                           f"Issues: {', '.join(review.get('issues', []))}\n"
                                           f"Suggestion: {review['suggestion']}\n"
                                           f"Please improve your response."
                            })
                            full_response = ""
                            continue  # Nochmal denken

                        elif verdict == "reject":
                            self.log.info("DeepThink: reject — answering directly")
                            deep_response = self.deepthink.think(
                                user_message, on_token=on_token,
                                conversation=active_history[-20:]
                            )
                            if deep_response:
                                full_response = f"🧠 {deep_response}"

                    break

            # Finale Assistant-Antwort in History
            active_history.append({"role": "assistant", "content": full_response.strip()})
            # Nur in Haupt-History + Disk speichern wenn nicht isoliert
            if active_history is self.conversation_history:
                # In-Memory History auf 50 Messages begrenzen
                if len(self.conversation_history) > 50:
                    self.conversation_history = self.conversation_history[-50:]
                self._save_conversation()
            else:
                # Isolierte History nach Task aufräumen (RAM freigeben)
                active_history.clear()
            return full_response.strip()

        except Exception as e:
            error_msg = f"[MORUK OS] Error: {str(e)}"
            self.log.error(f"Think error: {str(e)}", exc_info=True)
            # Fehlerhafte [SYSTEM]-Messages aus History entfernen
            while (active_history and
                   active_history[-1]["role"] == "user" and
                   active_history[-1]["content"].startswith("[SYSTEM]")):
                active_history.pop()
            if active_history and active_history[-1]["role"] == "user":
                active_history.pop()
            return error_msg

    def _strip_tool_calls(self, text: str) -> str:
        """Entfernt <tool_call> und <tool> Blöcke aus Text für die Anzeige."""
        cleaned = re.sub(r'<tool(?:_call)?>.*?</tool(?:_call)?>', '', text, flags=re.DOTALL)
        # Mehrfache Leerzeilen auf max 2 reduzieren
        while '\n\n\n' in cleaned:
            cleaned = cleaned.replace('\n\n\n', '\n\n')
        return cleaned.strip()

    def _filter_messages(self, messages: list) -> list:
        """
        Bereinigt Messages vor dem API-Call:
        - Entfernt Messages mit leerem/None content
        - Stellt sicher dass User/Assistant alternieren (Anthropic-Pflicht)
        - Letzte Message muss user sein
        """
        # 1. Leere Messages entfernen
        filtered = [m for m in messages if m.get("role") in ("user", "assistant")
                    and m.get("content") and str(m["content"]).strip()]

        # 2. Duplikate gleicher Rolle zusammenführen (keine zwei user/user hintereinander)
        merged = []
        for msg in filtered:
            if merged and merged[-1]["role"] == msg["role"]:
                # Gleiche Rolle: Inhalt anhängen
                merged[-1]["content"] = str(merged[-1]["content"]) + "\n" + str(msg["content"])
            else:
                merged.append({"role": msg["role"], "content": msg["content"]})

        # 3. Sicherstellen dass mit user beginnt
        while merged and merged[0]["role"] != "user":
            merged.pop(0)

        # 4. Sicherstellen dass mit user endet (Anthropic-Requirement)
        while merged and merged[-1]["role"] != "user":
            merged.pop()

        return merged if merged else [{"role": "user", "content": "Continue."}]


        """Entfernt <tool_call> und <tool> Blöcke aus Text für die Anzeige."""
        cleaned = re.sub(r'<tool(?:_call)?>\s*.*?\s*</tool(?:_call)?>', '', text, flags=re.DOTALL)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def _call_provider(self, system_prompt: str, history: list = None) -> str:
        model = self.settings.get("model", "")
        max_tokens = self.settings.get("max_tokens", 4096)
        temperature = self.settings.get("temperature", 0.7)
        messages = (history if history is not None else self.conversation_history)[-20:]

        if getattr(self, "_provider_type", "openai_compatible") == "anthropic":
            return self._call_anthropic(system_prompt, messages, model, max_tokens, temperature)
        else:
            return self._call_openai_compatible(system_prompt, messages, model, max_tokens, temperature)

    def _call_anthropic(self, system: str, messages: list, model: str, max_tokens: int, temperature: float) -> str:
        filtered = self._filter_messages(messages)
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=filtered
        )
        self.last_token_usage = {
            "input": response.usage.input_tokens,
            "output": response.usage.output_tokens,
            "total": response.usage.input_tokens + response.usage.output_tokens
        }
        self._save_token_usage()
        return response.content[0].text

    def _call_provider_stream(self, system_prompt: str, on_token=None, history: list = None) -> str:
        """Streaming version von _call_provider. Ruft on_token(str) für jedes Token auf."""
        model = self.settings.get("model", "")
        max_tokens = self.settings.get("max_tokens", 4096)
        temperature = self.settings.get("temperature", 0.7)
        messages = (history if history is not None else self.conversation_history)[-20:]

        if getattr(self, "_provider_type", "openai_compatible") == "anthropic":
            return self._call_anthropic_stream(system_prompt, messages, model, max_tokens, temperature, on_token)
        else:
            return self._call_openai_stream(system_prompt, messages, model, max_tokens, temperature, on_token)

    def _call_anthropic_stream(self, system, messages, model, max_tokens, temperature, on_token=None) -> str:
        """Anthropic Streaming mit Token-Tracking."""
        full_text = ""
        try:
            with self.client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=self._filter_messages(messages)
            ) as stream:
                for text in stream.text_stream:
                    full_text += text
                    if on_token:
                        on_token(text)
                try:
                    final_msg = stream.get_final_message()
                    if final_msg and final_msg.usage:
                        self.last_token_usage = {
                            "input": final_msg.usage.input_tokens,
                            "output": final_msg.usage.output_tokens,
                            "total": final_msg.usage.input_tokens + final_msg.usage.output_tokens
                        }
                        self._save_token_usage()
                except Exception:
                    pass  # Usage optional - kein Crash
        except Exception:
            return self._call_anthropic(system, messages, model, max_tokens, temperature)
        return full_text

    def _call_openai_stream(self, system, messages, model, max_tokens, temperature, on_token=None) -> str:
        """OpenAI-kompatibles Streaming."""
        oai_messages = self._build_oai_messages(system, messages)
        full_text = ""
        try:
            stream = self.client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=oai_messages,
                stream=True,
                stream_options={"include_usage": True}
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_text += token
                    if on_token:
                        on_token(token)
                if hasattr(chunk, "usage") and chunk.usage:
                    try:
                        self.last_token_usage = {
                            "input": chunk.usage.prompt_tokens,
                            "output": chunk.usage.completion_tokens,
                            "total": chunk.usage.total_tokens
                        }
                        self._save_token_usage()
                    except Exception:
                        pass
        except Exception:
            return self._call_openai_compatible(system, messages, model, max_tokens, temperature)
        return full_text

    def _call_openai_compatible(self, system: str, messages: list, model: str, max_tokens: int, temperature: float) -> str:
        """Provider-agnostischer Call mit automatischer Context-Reduktion."""
        oai_messages = self._build_oai_messages(system, messages)

        def make_call(msgs):
            response = self.client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=msgs
            )
            if hasattr(response, 'usage') and response.usage:
                self.last_token_usage = {
                    "input": getattr(response.usage, 'prompt_tokens', 0),
                    "output": getattr(response.usage, 'completion_tokens', 0),
                    "total": getattr(response.usage, 'total_tokens', 0)
                }
                self._save_token_usage()
            return response.choices[0].message.content or ""

        import time as _time
        # Rate limit backoff: 3 Versuche mit exponentialem Backoff
        for attempt in range(3):
            try:
                # Budget-Check vor jedem Call
                self._check_api_budget()
                return make_call(oai_messages)
            except Exception as e:
                error_str = str(e).lower()

                # Rate Limit → warten und retry
                if any(x in error_str for x in ("rate limit", "429", "too many requests", "ratelimit")):
                    wait = 2 ** attempt * 5  # 5s, 10s, 20s
                    self.log.warning(f"Rate limit hit (attempt {attempt+1}/3) — waiting {wait}s...")
                    _time.sleep(wait)
                    continue

                # Context zu lang → History reduzieren
                if any(x in error_str for x in ("500", "context", "too long", "limit", "length")):
                    for keep in (6, 4, 2):
                        if len(oai_messages) <= keep + 1:
                            continue
                        self.log.warning(f"Retrying with last {keep} messages (context reduction)...")
                        reduced = [oai_messages[0]] + oai_messages[-keep:]
                        try:
                            self._check_api_budget()
                            return make_call(reduced)
                        except Exception as e2:
                            self.log.warning(f"Retry with {keep} messages failed: {e2}")

                self.log.error(f"API Error (attempt {attempt+1}): {e}")
                if attempt == 2:
                    raise e
        raise RuntimeError("Max retries exceeded")

    def _filter_messages_oai(self, oai_messages: list) -> list:
        """Stellt sicher dass OAI-Messages korrekt alternieren (nach context-reduction)."""
        if not oai_messages:
            return oai_messages
        system_msgs = [m for m in oai_messages if m.get("role") == "system"]
        rest = [m for m in oai_messages if m.get("role") != "system"]
        # Alternierung sicherstellen
        merged = []
        for msg in rest:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["content"] = str(merged[-1]["content"]) + " " + str(msg["content"])
            else:
                merged.append(msg)
        # Muss mit user enden
        while merged and merged[-1]["role"] != "user":
            merged.pop()
        return system_msgs + merged if merged else system_msgs + [{"role": "user", "content": "Continue."}]

    def _build_oai_messages(self, system: str, messages: list) -> list:
        """Baut OpenAI-kompatible Message-Liste inkl. Vision-Support.
        Extrahiert aus _call_openai_stream und _call_openai_compatible um Duplikation zu vermeiden."""
        oai_messages = [{"role": "system", "content": system}]
        has_vis = self.has_vision()
        for msg in self._filter_messages(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                if has_vis and role == "user" and "[Attached image:" in str(content):
                    oai_messages.append({"role": role, "content": self._build_vision_content(str(content))})
                else:
                    oai_messages.append({"role": role, "content": str(content)})
        return oai_messages

    def has_vision(self) -> bool:
        """Prüft ob das aktive Model Vision unterstützt.
        Sucht aktives Model in model_configs falls active_model_config fehlt."""
        config = self.settings.get("active_model_config", {})

        # Fallback: Model-Config aus providers.*.model_configs dynamisch suchen
        if not config:
            active_model = self.settings.get("model", "")
            providers = self.settings.get("providers", {})
            for provider_data in providers.values():
                for mc in provider_data.get("model_configs", []):
                    if mc.get("name") == active_model:
                        config = mc
                        # Für nächsten Aufruf cachen
                        self.settings["active_model_config"] = mc
                        break
                if config:
                    break

        caps = config.get("capabilities", {})
        return caps.get("vision", False)

    def _save_token_usage(self):
        """Speichert Token-Nutzung kumulativ in data/token_usage.json."""
        if not self.last_token_usage:
            return
        try:
            usage_path = DATA_DIR / "token_usage.json"
            usage_path.parent.mkdir(parents=True, exist_ok=True)
            if usage_path.exists():
                with open(usage_path, "r") as f:
                    data = json.load(f)
            else:
                data = {"total_input": 0, "total_output": 0, "total_tokens": 0, "calls": 0, "sessions": []}
            data["total_input"] += self.last_token_usage.get("input", 0)
            data["total_output"] += self.last_token_usage.get("output", 0)
            data["total_tokens"] += self.last_token_usage.get("total", 0)
            data["calls"] += 1
            data.setdefault("sessions", []).append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "input": self.last_token_usage.get("input", 0),
                "output": self.last_token_usage.get("output", 0),
                "model": self.settings.get("model", "")
            })
            if len(data["sessions"]) > 100:
                data["sessions"] = data["sessions"][-100:]
            with open(usage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.log.error(f"Token-Save fehlgeschlagen: {e}")

    def _check_api_budget(self):
        """Prüft ob das API Budget überschritten wurde. Wirft Exception wenn Limit erreicht."""
        budget_limit = self.settings.get("api_budget_tokens", 0)  # 0 = kein Limit
        if budget_limit <= 0:
            return
        stats = self.get_token_stats()
        total = stats.get("total_tokens", 0)
        if total >= budget_limit:
            raise RuntimeError(
                f"API Budget erschöpft: {total:,} / {budget_limit:,} Tokens verwendet. "
                f"Limit in Settings erhöhen oder zurücksetzen."
            )
        # Warnung bei 80%
        if total >= budget_limit * 0.8:
            self.log.warning(f"⚠ API Budget bei {total/budget_limit:.0%}: {total:,}/{budget_limit:,} Tokens")

    def get_token_stats(self) -> dict:
        """Gibt kumulative Token-Statistiken zurück."""
        try:
            usage_path = DATA_DIR / "token_usage.json"
            if usage_path.exists():
                with open(usage_path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"total_input": 0, "total_output": 0, "total_tokens": 0, "calls": 0}

    def _get_vision_format(self) -> str:
        """Erkennt das Vision-Format des aktiven Providers automatisch.
        Returns: 'openai' | 'anthropic' | 'gemini'
        """
        # Anthropic hat eigenen Call-Path — hier nur für Vollständigkeit
        if getattr(self, "_provider_type", "") == "anthropic":
            return "anthropic"

        # Base-URL des aktiven Models prüfen
        base_url = ""
        model_config = self.settings.get("active_model_config", {})
        if model_config:
            base_url = model_config.get("base_url", "")
        if not base_url:
            base_url = self.settings.get("base_url", "")
        if not base_url:
            provider = self.settings.get("provider", "")
            base_url = self.settings.get("providers", {}).get(provider, {}).get("base_url", "")

        base_url_lower = base_url.lower()

        # Gemini — native oder OpenAI-compat Endpoint
        if "generativelanguage.googleapis.com" in base_url_lower:
            return "gemini"
        if "googleapis.com" in base_url_lower:
            return "gemini"

        # Anthropic
        if "anthropic.com" in base_url_lower:
            return "anthropic"

        # Alles andere (OpenAI, xAI/Grok, MiniMax, Ollama, etc.) → OpenAI-Format
        return "openai"

    def _build_image_block(self, b64: str, mime: str, fmt: str) -> dict:
        """Baut einen Image-Block im richtigen Format für den Provider."""
        if fmt == "anthropic":
            return {
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64}
            }
        elif fmt == "gemini":
            # Gemini native format
            return {
                "inline_data": {"mime_type": mime, "data": b64}
            }
        else:
            # OpenAI / Grok / MiniMax / DALL-E / Ollama / alle anderen
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"}
            }

    def _build_vision_content(self, text: str) -> list:
        """Baut Vision-Content-Blöcke universal für jeden Provider.
        Erkennt automatisch: OpenAI | Anthropic | Gemini | Custom.
        Gibt immer eine list zurück (niemals str)."""
        fmt = self._get_vision_format()
        content_parts = []

        pattern = r'\[Attached image: .+?\]\s*\n\[Image saved at: (.+?)\]'
        matches = list(re.finditer(pattern, text))

        if not matches:
            return [{"type": "text", "text": text}]

        mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}

        last_end = 0
        for match in matches:
            pre_text = text[last_end:match.start()].strip()
            if pre_text:
                content_parts.append({"type": "text", "text": pre_text})

            img_path = match.group(1).strip()
            if os.path.exists(img_path):
                try:
                    with open(img_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    ext = img_path.lower().rsplit(".", 1)[-1] if "." in img_path else "png"
                    mime = mime_map.get(ext, "image/png")
                    content_parts.append(self._build_image_block(b64, mime, fmt))
                    self.log.info(f"Vision: {fmt}-format, {ext}, {len(b64)//1024}KB")
                except Exception as e:
                    content_parts.append({"type": "text", "text": f"[Image load error: {e}]"})
            else:
                content_parts.append({"type": "text", "text": f"[Image not found: {img_path}]"})

            last_end = match.end()

        remaining = text[last_end:].strip()
        remaining = re.sub(r'---\s*ATTACHED FILES\s*---', '', remaining).strip()
        if remaining:
            content_parts.append({"type": "text", "text": remaining})

        return content_parts if content_parts else [{"type": "text", "text": text}]

    def get_conversation_summary(self) -> str:
        count = len(self.conversation_history)
        if count == 0:
            return "Keine vorherige Konversation."
        return f"{count} Messages in History."

    def validate_action(self, tool: str, params: dict, user_query: str) -> bool:
        """
        Nutzt MiniMax M2.5, um zu entscheiden, ob ein Tool-Call sicher ist.
        """
        # Wir bauen einen sehr kurzen, strengen Prompt
        prompt = f"""
        AUDIT-AUFTRAG:
        User fragt: "{user_query}"
        Geplante Aktion: Tool "{tool}" mit Parametern {json.dumps(params)}

        ENTSCHEIDE:
        Ist diese Aktion sicher und führt sie NICHT zu Datenverlust oder Systemschäden?
        (Bei 'write_file': Ist der Code vollständig?)

        Antworte NUR mit 'YES' oder 'NO'.
        """
        
        try:
            # Wir nutzen deine bestehende think-Logik für eine schnelle Antwort
            response = self.think(prompt, max_tokens=10) 
            return "YES" in response.upper()
        except Exception as e:
            log.error(f"DeepThink Validation Error: {e}")
            return True # Im Fehlerfall lassen wir es durch, um den Flow nicht zu killen
    
