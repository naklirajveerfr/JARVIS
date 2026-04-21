# JARVIS — Voice AI Assistant

A Jarvis-style desktop AI assistant with voice control, system monitoring, and computer automation.

## Structure
```
jarvis/
├── launch.py              ← START HERE
├── requirements.txt
├── backend/
│   ├── main.py            ← WebSocket server + voice loop
│   ├── groq_client.py     ← AI brain
|   ├── api.txt            ← Put groq api key here
│   ├── system_control.py  ← Open apps, type text, system info
│   └── web_search.py      ← DuckDuckGo (no API key)
└── frontend/
    └── index.html         ← HUD
```

## Setup

> [!IMPORTANT]
> Add your Groq API key in backend/api.txt (you can get one for free).

### 1. Install Python deps
```bash
pip install -r requirements.txt
```

On Linux you may also need:
```bash
sudo apt install python3-pyaudio portaudio19-dev espeak
```

### 3. Launch JARVIS
```bash
python launch.py
```
This starts the backend and opens the HUD in your browser.

---

| Say                               | What happens                              |
| --------------------------------- | ----------------------------------------- |
| "What's my CPU usage?"            | Shows top CPU & memory usage processes    |
| "Show running processes"          | Lists active processes                    |
| "Open {appname}"                  | Launches any installed app or system tool |
| "Open {website}"                  | Opens a website in browser                |
| "Type Hello world"                | Types text at cursor                      |
| "Search for Python tutorials"     | Opens browser search                      |
| "Run command ipconfig"            | Executes system command                   |
| "List files"                      | Lists files in home directory             |
| "List files in {folder}"          | Lists files in specified folder           |
| "Read file {filename}"            | Reads a text file                         |
| "Write file {filename} {content}" | Creates/writes to a file                  |
| "Delete file {filename}"          | Deletes file (recycle bin)                |
| "Search file {query}"             | Searches for files                        |
| "Open file {filename}"            | Opens a file                              |
| "What's on my screen?"            | Shows active & open windows               |
| "Get clipboard"                   | Reads clipboard text                      |
| "What time is it?"                | Tells current time                        |
| "System status"                   | Full system context                       |
| Anything else                     | Goes to Groq AI                           |


> [!CAUTION]
> Jarvis is currently in beta and may occasionally make mistakes.
>


## Troubleshooting

- **Mic not working**: Check `speech_recognition` mic access. On Windows, allow mic in Privacy settings.
- **PyAudio install fail (Windows)**: Download the right `.whl` from https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
- **pyautogui fail on Linux**: `sudo apt install python3-xlib`
