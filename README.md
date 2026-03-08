<div align="center">

```
███╗   ███╗ ██████╗ ██████╗ ██╗   ██╗██╗  ██╗     ██████╗ ███████╗
████╗ ████║██╔═══██╗██╔══██╗██║   ██║██║ ██╔╝    ██╔═══██╗██╔════╝
██╔████╔██║██║   ██║██████╔╝██║   ██║█████╔╝     ██║   ██║███████╗
██║╚██╔╝██║██║   ██║██╔══██╗██║   ██║██╔═██╗     ██║   ██║╚════██║
██║ ╚═╝ ██║╚██████╔╝██║  ██║╚██████╔╝██║  ██╗    ╚██████╔╝███████║
╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝     ╚═════╝ ╚══════╝
```

**An autonomous AI operating system that thinks, learns, and acts — on your machine.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![PyQt6](https://img.shields.io/badge/UI-PyQt6-green?style=flat-square)](https://pypi.org/project/PyQt6/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux-orange?style=flat-square&logo=linux)](https://linux.org)

</div>

---

## What is Moruk OS?

Moruk OS is a **fully autonomous AI agent** running locally on your Linux machine. It's not a chatbot — it's an operating system layer that can browse the web, write and execute code, manage files, monitor your system, and complete multi-step projects, all while learning from every interaction.

Think of it as having a senior developer, researcher, and system administrator available 24/7 — powered by Claude, GPT, Gemini, or any OpenAI-compatible model.

---

## Features

### 🧠 Multi-Model Brain
Connect any AI provider via a single interface. Claude, GPT-4, Gemini, Groq, DeepSeek, Kimi — switch models mid-conversation or let the Model Router auto-select the best one for the task.

### ⚡ Autonomous Loop
Set Autonomy ON and Moruk OS will independently pursue goals, monitor progress, reflect on failures, and retry — without you lifting a finger.

### 🏗 Project Manager
Describe a project in plain language. Moruk OS decomposes it into subtasks using DeepThink, executes them in parallel where possible, reviews results, and retries failed steps.

### 🔍 DeepThink
A secondary reasoning layer that reviews critical actions before execution. Catches mistakes, validates code, and prevents destructive commands.

### 💾 Persistent Memory
Vector-based semantic memory + SQLite. Moruk OS remembers what you told it weeks ago and retrieves relevant context automatically.

### 🛰 Web Monitor
Watch any website for changes. Moruk OS notifies you — and can react autonomously — when content updates.

### 🔴 Live Activity
Real-time window showing every tool call, reasoning step, and decision as it happens.

### 🔌 Plugin System
Drop a `.py` file into `plugins/` and it's instantly available as a tool. No restarts, no config.

### 👤 User Profile
Moruk OS learns your preferences, working style, and domain expertise over time — and adapts its behavior accordingly.

---

## Screenshots

> Coming soon — contributions welcome!

---

## Quick Start

### Requirements

- Linux (Ubuntu 20.04+ recommended)
- Python 3.10+
- At least one API key: [Anthropic](https://console.anthropic.com), [OpenAI](https://platform.openai.com), or [Google AI](https://aistudio.google.com)

### Install

```bash
git clone https://github.com/FiratBulut/Moruk-OS.git
cd moruk-os
chmod +x install.sh
./install.sh
```

### Run

```bash
./run.sh
```

On first launch, open Settings (⚙) and add your API key.

---

## Supported AI Providers

| Provider | Models | Notes |
|----------|--------|-------|
| Anthropic | Claude 3.5, Claude 3 Opus/Sonnet/Haiku | Recommended |
| OpenAI | GPT-4o, GPT-4, GPT-3.5 | Full support |
| Google | Gemini 1.5 Pro/Flash | Vision + native search |
| Groq | Llama 3, Mixtral | Ultra-fast inference |
| DeepSeek | DeepSeek-V2, Coder | Excellent for code |
| Kimi | Moonshot | Long context |
| Any OpenAI-compatible | — | Custom base URL |

---

## Architecture

```
moruk-os/
├── core/
│   ├── brain.py           # Central AI reasoning engine
│   ├── tool_router.py     # Tool dispatch + reflection
│   ├── autonomy_loop.py   # Autonomous goal pursuit
│   ├── project_manager.py # Multi-step project execution
│   ├── goal_engine.py     # Proactive goal generation
│   ├── deepthink.py       # Secondary reasoning layer
│   ├── memory.py          # Short-term conversation memory
│   ├── vector_memory.py   # Long-term semantic memory
│   ├── reflector.py       # Self-improvement via reflection
│   ├── model_router.py    # Automatic model selection
│   └── monitor_engine.py  # Web change detection
├── ui/
│   ├── main_window.py     # Main application window
│   ├── sidebar.py         # Tasks, Memory, Reflect, Goals
│   ├── live_activity_window.py  # Real-time tool viewer
│   └── settings_dialog.py # API keys + configuration
├── plugins/               # Drop-in tool plugins
│   ├── web_search.py
│   ├── web_scraper.py
│   ├── file_manager.py
│   ├── browser.py
│   ├── vision.py
│   ├── voice.py
│   └── ...
├── data/                  # Runtime data (memory, sessions, logs)
├── models/                # Local TTS models (Piper)
├── main.py
├── run.sh
└── install.sh
```

---

## Plugin Development

Creating a plugin takes under 2 minutes:

```python
# plugins/my_tool.py

PLUGIN_NAME = "my_tool"
PLUGIN_DESCRIPTION = "Does something useful. Params: input (str)."
PLUGIN_PARAMS = {"input": "The input string"}

def execute(params):
    result = do_something(params.get("input", ""))
    return {"success": True, "result": result}
```

That's it. Moruk OS picks it up automatically on next launch (or after `list_tools` is called).

---

## Configuration

All settings are stored in `config/settings.json`. You can also configure everything via the Settings dialog (⚙ button in the UI):

- **API Keys**: Multiple providers, tested on save
- **Default Model**: Per-provider model selection
- **Voice**: Google Neural2 TTS (requires Gemini key)
- **Vision**: Automatic screenshot analysis
- **DeepThink**: Secondary model for critical reasoning
- **System Prompt**: Fully customizable agent personality

---

## Contributing

Pull requests are welcome. For major changes, please open an issue first.

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## Roadmap

- [ ] Windows / macOS support
- [ ] Web UI (browser-based interface)
- [ ] Plugin marketplace
- [ ] Multi-instance / distributed agents
- [ ] Voice-first interaction mode
- [ ] Mobile companion app

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built with obsession by someone who wanted a real AI OS, not just another chatbot.

**Star ⭐ if Moruk OS blew your mind.**

</div>
