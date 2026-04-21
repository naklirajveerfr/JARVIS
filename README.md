# JARVIS — Voice AI Assistant

A Jarvis-style desktop AI assistant with voice control, system monitoring, and computer automation.

## Structure
```
jarvis/
├── launch.py              ← START HERE
├── requirements.txt
├── backend/
│   ├── main.py            ← WebSocket server + voice loop
│   ├── ollama_client.py   ← AI brain (Ollama)
│   ├── system_control.py  ← Open apps, type text, system info
│   └── web_search.py      ← DuckDuckGo (no API key)
└── frontend/
    └── index.html         ← HUD (open in browser)
```

## Setup

### 1. Install Python deps
```bash
pip install -r requirements.txt
```

On Linux you may also need:
```bash
sudo apt install python3-pyaudio portaudio19-dev espeak
```

### 2. Start Ollama + pull a model
```bash
ollama serve          # in a terminal, keep running
ollama pull llama3    # or: mistral, llama3.2, phi3
```

### 3. Launch JARVIS
```bash
python launch.py
```

This starts the backend and opens the HUD in your browser.

---

## Voice Commands

| Say | What happens |
|-----|-------------|
| "What's my CPU usage?" | Shows live system stats |
| "Open Chrome" | Launches Chrome |
| "Open notepad" | Opens text editor |
| "Type Hello world" | Types text at cursor |
| "Search for Python tutorials" | DuckDuckGo search |
| "What time is it?" | Tells current time |
| Anything else | Goes to Ollama AI |

---

## Changing the AI Model

Edit `backend/ollama_client.py`, line 4:
```python
MODEL = "llama3"   # change to: mistral, llama3.2, phi3, gemma2, etc.
```

---

## Troubleshooting

- **Mic not working**: Check `speech_recognition` mic access. On Windows, allow mic in Privacy settings.
- **"Ollama not running"**: Run `ollama serve` first.
- **PyAudio install fail (Windows)**: Download the right `.whl` from https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
- **pyautogui fail on Linux**: `sudo apt install python3-xlib`
