import asyncio
import json
import subprocess
import ctypes
import ctypes.wintypes
import threading
import time
import re
from datetime import datetime
from pathlib import Path

import psutil
import websockets
import speech_recognition as sr

from groq_client import ask_groq, init_client, clear_history
from web_search import duckduckgo_search
from system_control import (
    open_app, type_text, get_full_context,
    list_files, read_file, write_file, delete_file, search_files,
    open_file, run_command, discord_send_message, get_open_windows,
    get_active_window_title,
)

HWND_FILE = Path(__file__).parent / ".jarvis_hwnd"

# ── TTS via pyttsx3 (fast — no PowerShell cold-start) ────────────────────────
# Install: pip install pyttsx3
# Falls back to slow SAPI PowerShell if pyttsx3 not available.

try:
    import pyttsx3 as _pyttsx3
    # Only use pyttsx3 to enumerate voices at startup — do NOT keep a shared engine.
    # pyttsx3's runAndWait() corrupts the COM event loop when reused across calls
    # from a background thread, causing it to silently die after the first call.
    _voice_enum_engine = _pyttsx3.init()
    _all_voices = _voice_enum_engine.getProperty("voices")
    _voice_enum_engine.stop()
    PYTTSX3_OK = True
except Exception:
    PYTTSX3_OK = False
    _all_voices = []

# Voice state — index into available voices
_current_voice_index = 0

def get_available_voices() -> list[dict]:
    """Return list of {id, name} for all installed TTS voices."""
    return [{"id": i, "name": v.name} for i, v in enumerate(_all_voices)]

def set_voice(index: int) -> str:
    """Switch TTS voice by index. Returns confirmation string."""
    global _current_voice_index
    if not PYTTSX3_OK:
        return "pyttsx3 not available — voice selection not supported."
    if index < 0 or index >= len(_all_voices):
        return f"Invalid voice index {index}. Available: 0–{len(_all_voices)-1}."
    _current_voice_index = index
    return f"Voice changed to: {_all_voices[index].name}"

# TTS queue — single background thread, fresh engine per utterance
tts_queue: list[str] = []
tts_event = threading.Event()
suppress_tts_flag = False
_tts_lock = threading.Lock()

def _speak_pyttsx3(text: str):
    """Speak by creating a fresh pyttsx3 engine each call.
    This avoids the COM/event-loop corruption that kills reused engines."""
    with _tts_lock:
        try:
            engine = _pyttsx3.init()
            engine.setProperty("rate", 185)
            engine.setProperty("volume", 1.0)
            if _all_voices and _current_voice_index < len(_all_voices):
                engine.setProperty("voice", _all_voices[_current_voice_index].id)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"[TTS pyttsx3 error] {e}")

def _speak_sapi_fallback(text: str):
    """Fallback: PowerShell SAPI (slow, only used if pyttsx3 unavailable)."""
    safe = text.replace('"', "'").replace("\n", " ").replace(";", ",")
    script = (
        'Add-Type -AssemblyName System.Speech; '
        '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
        '$s.Rate = 1; '
        f'$s.Speak("{safe}");'
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        print(f"[TTS SAPI error] {e}")

def tts_worker():
    while True:
        tts_event.wait()
        tts_event.clear()
        while tts_queue:
            text = tts_queue.pop(0)
            if not suppress_tts_flag:
                if PYTTSX3_OK:
                    _speak_pyttsx3(text)
                else:
                    _speak_sapi_fallback(text)

threading.Thread(target=tts_worker, daemon=True).start()

def speak(text: str):
    print(f"[SPEAK] {text}")
    tts_queue.append(text)
    tts_event.set()

# ── Window focus ──────────────────────────────────────────────────────────────
def focus_jarvis_window():
    try:
        if not HWND_FILE.exists():
            return
        hwnd = int(HWND_FILE.read_text().strip())
        if not hwnd:
            return
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    except Exception as e:
        print(f"[FOCUS error] {e}")

# ── WebSocket state ───────────────────────────────────────────────────────────
connected_clients: set = set()
loop: asyncio.AbstractEventLoop = None

def broadcast_sync(data: dict):
    if loop is None:
        return
    asyncio.run_coroutine_threadsafe(broadcast(json.dumps(data)), loop)

async def broadcast(msg: str):
    dead = set()
    for ws in connected_clients:
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    connected_clients.difference_update(dead)

def log_intel(action: str, detail: str, status: str = "ok"):
    broadcast_sync({
        "type": "intel",
        "action": action,
        "detail": detail,
        "status": status,
        "time": datetime.now().strftime("%H:%M:%S"),
    })

# ── Speech recognition ────────────────────────────────────────────────────────
recognizer = sr.Recognizer()
recognizer.energy_threshold = 400
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.8

WAKE_WORD = "groq"          # ← changed from "claude" to "groq"
COMMAND_TIMEOUT = 7

def transcribe_audio(audio: sr.AudioData) -> str:
    return recognizer.recognize_google(audio)

def listen_loop():
    # Guard: if pyaudio is missing, print a clear message and exit gracefully
    try:
        import pyaudio  # noqa: F401
    except ImportError:
        print(
            "[MIC] PyAudio not installed — voice input disabled.\n"
            "      Fix: pip install pipwin && pipwin install pyaudio\n"
            "      Or:  pip install pyaudio  (if pre-built wheel available)\n"
            "      JARVIS will still work via text input."
        )
        broadcast_sync({"type": "status", "value": "no_mic"})
        return

    try:
        mic = sr.Microphone()
    except Exception as e:
        print(f"[MIC] Could not open microphone: {e}")
        broadcast_sync({"type": "status", "value": "no_mic"})
        return

    with mic as source:
        print("[MIC] Calibrating for ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=1.5)
        print(f"[MIC] Ready — listening for wake word: '{WAKE_WORD}'")
        broadcast_sync({"type": "status", "value": "wake_listen"})

        while True:
            # ── passive listen for wake word ──────────────────────────
            try:
                audio = recognizer.listen(source, timeout=None, phrase_time_limit=5)
                heard = transcribe_audio(audio).lower()
                print(f"[PASSIVE] {heard}")
            except sr.UnknownValueError:
                continue
            except Exception as e:
                print(f"[PASSIVE error] {e}")
                time.sleep(0.5)
                continue

            if WAKE_WORD not in heard:
                continue

            # ── wake word detected ────────────────────────────────────
            print(f"[WAKE] '{WAKE_WORD}' detected!")
            focus_jarvis_window()
            broadcast_sync({"type": "status", "value": "listening"})
            broadcast_sync({"type": "wake", "value": True})
            speak("Yes?")

            # Check if command was spoken in the same utterance as wake word
            inline = re.sub(
                rf".*\b{re.escape(WAKE_WORD)}\b[,.]?\s*", "", heard, flags=re.I
            ).strip()
            if len(inline) > 2:
                broadcast_sync({"type": "transcript", "text": inline})
                threading.Thread(
                    target=handle_command, args=(inline,), daemon=True
                ).start()
                broadcast_sync({"type": "status", "value": "wake_listen"})
                continue

            # ── realtime streaming listen for the command utterance ───
            # Collect short audio chunks and broadcast each partial result
            # so the UI shows what you're saying in real time.
            collected_chunks: list[str] = []
            deadline = time.time() + COMMAND_TIMEOUT

            broadcast_sync({"type": "interim_transcript", "text": ""})  # clear UI

            while time.time() < deadline:
                remaining = deadline - time.time()
                chunk_limit = min(2.0, remaining)  # 2-second chunks for low latency
                if chunk_limit < 0.3:
                    break
                try:
                    chunk_audio = recognizer.listen(
                        source,
                        timeout=chunk_limit,
                        phrase_time_limit=chunk_limit,
                    )
                    chunk_text = transcribe_audio(chunk_audio).strip()
                    if chunk_text:
                        collected_chunks.append(chunk_text)
                        partial = " ".join(collected_chunks)
                        print(f"[INTERIM] {partial}")
                        # Send as interim so UI can show it live
                        broadcast_sync({"type": "interim_transcript", "text": partial})
                        # If the chunk ends with a sentence-ending punctuation or
                        # is long enough, treat it as a complete command
                        if (chunk_text.rstrip()[-1] in ".?!" or
                                len(partial.split()) >= 12):
                            break
                except sr.WaitTimeoutError:
                    # Silence = user stopped speaking, flush what we have
                    break
                except sr.UnknownValueError:
                    # Couldn't parse this chunk — silence or noise, stop collecting
                    break
                except Exception as e:
                    print(f"[CHUNK error] {e}")
                    break

            if collected_chunks:
                command = " ".join(collected_chunks)
                print(f"[CMD] {command}")
                # Promote interim to final transcript
                broadcast_sync({"type": "transcript", "text": command})
                broadcast_sync({"type": "status", "value": "processing"})
                threading.Thread(
                    target=handle_command, args=(command,), daemon=True
                ).start()
            else:
                speak("I didn't catch that.")

            broadcast_sync({"type": "status", "value": "wake_listen"})

# ── Context builder ───────────────────────────────────────────────────────────
def build_context_prompt(user_text: str) -> str:
    """
    Build a short context block so the AI knows current state.
    Kept deliberately brief to avoid confusing the tool-calling model.
    """
    try:
        ctx = get_full_context()
        context_block = (
            f"[CONTEXT] time={ctx['time']} | user={ctx['username']} "
            f"| active_window={ctx['active_window']}\n"
            f"User: {user_text}"
        )
        return context_block
    except Exception:
        return user_text

# ── Command router ────────────────────────────────────────────────────────────
def handle_command(text: str):
    lower = text.lower().strip()

    # ── What windows are open ─────────────────────────────────────────────────
    if any(k in lower for k in [
        "what's open", "whats open", "running apps", "open windows", "what are you seeing"
    ]):
        windows = get_open_windows()
        active = get_active_window_title()
        msg = (
            f"You have {len(windows)} windows open. "
            f"Active: {active}. "
            f"Others: {', '.join(windows[:6])}."
        )
        broadcast_sync({"type": "response", "text": msg, "source": "system"})
        log_intel("AWARENESS", f"Active: {active} | {len(windows)} windows open")
        speak(msg)
        return

    # ── Open app (simple prefix match) ───────────────────────────────────────
    if lower.startswith("open ") and not any(
        x in lower for x in ["open file", "open folder", "open document"]
    ):
        target = re.sub(r"^open\s+", "", lower).strip()
        log_intel("LAUNCH", f"Opening: {target}", "ok")
        result = open_app(target)
        broadcast_sync({"type": "response", "text": result, "source": "system"})
        log_intel("LAUNCH", result)
        speak(result)
        return

    # ── Open URL ──────────────────────────────────────────────────────────────
    if any(k in lower for k in ["go to ", "open website", "open url", "browse to "]):
        url = re.sub(r"(go to|open website|open url|browse to)\s*", "", lower).strip()
        if not url.startswith("http"):
            url = "https://" + url
        import webbrowser
        webbrowser.open(url)
        msg = f"Opened {url}."
        broadcast_sync({"type": "response", "text": msg, "source": "system"})
        log_intel("BROWSER", url)
        speak(msg)
        return

    # ── Web search ────────────────────────────────────────────────────────────
    if (
        lower.startswith("search for")
        or lower.startswith("search ")
        or "look up" in lower
    ):
        query = re.sub(r"^(search for|search|look up)\s*", "", lower, flags=re.I).strip()
        broadcast_sync({"type": "status", "value": "searching"})
        log_intel("SEARCH", f"Searching: {query}")
        results = duckduckgo_search(query)
        snippet = results[0]["snippet"] if results else "No results found."
        msg = f"Here's what I found about {query}: {snippet}"
        broadcast_sync({
            "type": "response", "text": msg,
            "source": "search", "results": results
        })
        log_intel("SEARCH", f"Got {len(results)} results for '{query}'")
        speak(msg)
        return

    # ── Type text ─────────────────────────────────────────────────────────────
    if lower.startswith("type "):
        to_type = text[5:]
        result = type_text(to_type)
        broadcast_sync({"type": "response", "text": result, "source": "system"})
        log_intel("KEYBOARD", f"Typed: {to_type[:40]}")
        speak(result)
        return

    # ── Time / date ───────────────────────────────────────────────────────────
    if re.search(r"\b(time|date|day|today)\b", lower):
        now = datetime.now()
        msg = f"It's {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d %Y')}."
        broadcast_sync({"type": "response", "text": msg, "source": "system"})
        speak(msg)
        return

    # ── Voice selection ───────────────────────────────────────────────────────
    if "change voice" in lower or "switch voice" in lower or "set voice" in lower:
        # e.g. "change voice to 1" or "switch voice 2"
        match = re.search(r"\d+", lower)
        if match:
            idx = int(match.group())
            result = set_voice(idx)
        else:
            voices = get_available_voices()
            if voices:
                result = "Available voices: " + ", ".join(
                    f"{v['id']}: {v['name']}" for v in voices
                )
            else:
                result = "No voices found. Make sure pyttsx3 is installed."
        broadcast_sync({"type": "response", "text": result, "source": "system"})
        speak(result)
        return

    # ── Default → Groq AI (with tool calling) ─────────────────────────────────
    broadcast_sync({"type": "status", "value": "thinking"})
    log_intel("AI", f"Query: {text[:60]}")
    prompt_with_context = build_context_prompt(text)
    response = ask_groq(prompt_with_context)
    broadcast_sync({"type": "response", "text": response, "source": "ai"})
    log_intel("AI", f"Response: {response[:60]}")
    speak(response)
    broadcast_sync({"type": "status", "value": "wake_listen"})

# ── WebSocket handler ─────────────────────────────────────────────────────────
async def handler(websocket):
    global suppress_tts_flag
    connected_clients.add(websocket)
    print(f"[+] Client connected")

    try:
        # Send available voices on connect so frontend can show a picker
        voices = get_available_voices()
        await websocket.send(json.dumps({
            "type": "init",
            "has_key": True,
            "voices": voices,
        }))

        async for raw in websocket:
            msg = json.loads(raw)
            action = msg.get("action")

            if action == "text_command":
                cmd = msg.get("text", "")
                if cmd:
                    await websocket.send(json.dumps({"type": "transcript", "text": cmd}))
                    threading.Thread(
                        target=handle_command, args=(cmd,), daemon=True
                    ).start()

            elif action == "set_voice":
                idx = msg.get("index", 0)
                result = set_voice(idx)
                await websocket.send(json.dumps({
                    "type": "response", "text": result, "source": "system"
                }))

            elif action == "list_voices":
                voices = get_available_voices()
                await websocket.send(json.dumps({"type": "voices", "data": voices}))

            elif action == "list_files":
                result = list_files(msg.get("path"))
                await websocket.send(json.dumps({"type": "files", "data": result}))

            elif action == "read_file":
                result = read_file(msg.get("path", ""))
                await websocket.send(json.dumps({"type": "file_content", "data": result}))

            elif action == "run_command":
                result = run_command(msg.get("cmd", ""))
                await websocket.send(json.dumps({"type": "shell_result", "data": result}))

            elif action == "suppress_tts":
                tts_queue.clear()

            elif action == "clear_history":
                clear_history()
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": "Conversation history cleared.",
                    "source": "system",
                }))
                log_intel("MEMORY", "Conversation history cleared.")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)

# ── Entry point ───────────────────────────────────────────────────────────────
async def main():
    global loop
    loop = asyncio.get_event_loop()

    try:
        init_client()
        print("[✓] Groq client initialized")
    except Exception as e:
        print(f"[!] Groq init failed: {e}")

    # Print available TTS voices at startup
    voices = get_available_voices()
    if voices:
        print(f"[TTS] {len(voices)} voice(s) available:")
        for v in voices:
            print(f"      [{v['id']}] {v['name']}")
        print(f"[TTS] Using voice [{_current_voice_index}]: {voices[_current_voice_index]['name']}")
    else:
        print("[TTS] pyttsx3 not available — using slow PowerShell SAPI fallback.")
        print("      Fix: pip install pyttsx3")

    threading.Thread(target=listen_loop, daemon=True).start()
    print("JARVIS backend starting on ws://localhost:8765")

    async with websockets.serve(handler, "localhost", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())