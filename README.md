# NOVA — Voice/Text AI Assistant

Multi-modal AI assistant with desktop GUI, web interface, and CLI. Runs on Ollama.

<a herf="Can you tell me about world events?">demo</a>

## Quick Start

```bash
pip install -r requirements.txt
ollama pull qwen2.5:1.5b
python ui2_small.py    # V2 Small desktop GUI (green theme, for 1B-3B models)
```

## Entry Points

| Command | Version | Mode |
|---|---|---|
| `python ui2.py` | **V2** | Desktop GUI (Tkinter, animated HUD) |
| `python web_v2.py` | **V2** | Web server on `:9090` |
| `python jarvis_v2.py` | **V2** | CLI — native tool-calling agent |
| `python ui2_small.py` | **V2** | Desktop GUI — JSON-mode for small models (green theme) |
| `python web_v2_small.py` | **V2** | Web server on `:9091` — JSON-mode for small models |
| `python jarvis_v2_small.py` | **V2** | CLI — JSON-mode agent for small models |
| `python ui.py` | V1 | Desktop GUI (Tkinter) |
| `python web.py` | V1 | Web server on `:8080` + file manager |
| `python jarvis.py` | V1 | CLI — command-router agent |
| `python nova.py` | V1 | Earliest CLI version |

## V2 vs V1

| | V2 (`jarvis_v2.py`) | V2 Small (`jarvis_v2_small.py`) | V1 (`jarvis.py`) |
|---|---|---|---|
| **Approach** | Native Ollama `tool_calls` | JSON-mode routing (`format: json`) | JSON command router |
| **Model need** | 7B+ (good tool calling) | 1B+ (any JSON-capable model) | 3B+ |
| **Multi-step** | Yes (10-turn loop) | Yes (8-turn loop) | Single-turn |
| **Web search** | Yes | Yes | Yes |
| **File ops** | Yes | Yes | Yes |
| **Browser** | No | No | Yes |
| **Discord** | No | No | Yes |

## Configuration

Edit `jarvis.py` constants:

```python
CHAT_MODEL = "llama3.2:latest"   # change model here
WEATHER_LOCATION = "Toronto"      # your city
WORKSPACE_DIR = "./workspace/"    # file storage
```

## Raspberry Pi 4 (8GB) — Model Guide

### Recommended Models

| Model | Size | Speed (Pi 4) | Quality | Pull command |
|---|---|---|---|---|
| **Qwen2.5 1.5B** | ~1.0 GB | ~5-7 tok/s | Good | `ollama pull qwen2.5:1.5b` |
| **TinyLlama 1.1B** | ~0.6 GB | ~8 tok/s | Decent | `ollama pull tinylm:1.1b` |
| **Llama 3.2 1B** | ~0.7 GB | ~6-8 tok/s | Decent | `ollama pull llama3.2:1b` |
| **Gemma 2 2B** | ~1.5 GB | ~3-4 tok/s | Good | `ollama pull gemma2:2b` |
| **Phi-3 Mini** | ~2.3 GB | ~2-3 tok/s | Great | `ollama pull phi3:mini` |

**Sweet spot: Qwen2.5 1.5B** — best quality-to-speed ratio on a Pi 4.

### Running on Pi

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a small model
ollama pull qwen2.5:1.5b

# Edit config in jarvis.py
# CHAT_MODEL = "qwen2.5:1.5b"

# Use the small-model agent (JSON-mode, no native tool_calls needed)
python jarvis_v2_small.py

# Or the web interface
python web_v2_small.py

# Or the desktop GUI
python ui2_small.py
```

**Tips:**
- Use `jarvis_v2_small.py` on Pi — it uses JSON-mode routing instead of native `tool_calls`, which small models handle more reliably
- NVMe SSD via USB 3.0 is strongly recommended over microSD for model loading speed
- Active cooling (heatsink + fan) prevents thermal throttling during inference
- Qwen2.5 1.5B gives the best balance; Phi-3 Mini if you want higher quality and can tolerate slower responses
