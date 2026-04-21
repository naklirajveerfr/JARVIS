#!/usr/bin/env python3
"""
JARVIS launcher — starts the backend and opens the HUD in a standalone window.
Run: python launch.py
"""
import subprocess
import sys
import os
import time
import ctypes
import ctypes.wintypes
import threading
from pathlib import Path

ROOT = Path(__file__).parent
BACKEND = ROOT / "backend" / "main.py"
FRONTEND = ROOT / "frontend" / "index.html"
HWND_FILE = ROOT / "backend" / ".jarvis_hwnd"  # shared with backend

def check_ollama():
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=2)
        return True
    except Exception:
        return False

def install_deps():
    print("[*] Installing dependencies...")
    pkgs = ["websockets", "speechrecognition", "psutil",
            "pyautogui", "requests", "pywebview"]
    subprocess.check_call([sys.executable, "-m", "pip", "install"] + pkgs + ["--quiet"])

def start_backend():
    if not BACKEND.exists():
        print(f"\n[!] Cannot find backend at {BACKEND}")
        sys.exit(1)
    return subprocess.Popen(
        [sys.executable, str(BACKEND)],
        cwd=str(BACKEND.parent)
    )

def wait_for_backend(timeout=20):
    """Stronger wait with multiple checks."""
    import socket
    import time
    print("[*] Waiting for backend WebSocket server (up to 20s)...")
    
    start = time.time()
    attempts = 0
    while time.time() - start < timeout:
        attempts += 1
        try:
            s = socket.create_connection(("localhost", 8765), timeout=1.5)
            s.close()
            print(f"[✓] Backend ready after {attempts} attempts")
            return True
        except Exception:
            time.sleep(0.6)
    
    print("[!] Backend still not responding on port 8765 — continuing anyway")
    return False


# In the main part, replace the waiting section with this:
print("[*] Starting backend...")
backend_proc = start_backend()

if wait_for_backend():
    print("[✓] Backend ready")
    time.sleep(2.0)          # ← Extra delay is very important
else:
    print("[!] Backend slow — continuing anyway")
    time.sleep(3.0)

print("[*] Opening JARVIS HUD...")
def find_and_save_hwnd():
    """Find the JARVIS window by title and save its HWND to a file."""
    user32 = ctypes.windll.user32
    found = [None]

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if "JARVIS" in buf.value:
                found[0] = hwnd
                return False
        return True

    # Poll until window appears (up to 5s)
    for _ in range(20):
        user32.EnumWindows(cb, 0)
        if found[0]:
            HWND_FILE.write_text(str(found[0]))
            print(f"[✓] Window HWND saved: {found[0]}")
            return
        time.sleep(0.25)

    print("[!] Could not find JARVIS window handle")

if __name__ == "__main__":
    print("=" * 50)
    print("  JARVIS — Voice AI Assistant")
    print("=" * 50)

    if not check_ollama():
        print("\n[!] Ollama is not running — AI responses will fail.\n")
    else:
        print("[✓] Ollama detected")

    try:
        import websockets, psutil, pyautogui, speech_recognition, webview
        print("[✓] Dependencies OK")
    except ImportError as e:
        print(f"[!] Missing: {e}. Installing...")
        install_deps()
        import webview

    # Clean up old hwnd file
    if HWND_FILE.exists():
        HWND_FILE.unlink()

    print("[*] Starting backend...")
    backend_proc = start_backend()

    print("[*] Waiting for backend...")
    if wait_for_backend():
        print("[✓] Backend ready")
        time.sleep(1.2)        # ← Add this delay
    else:
        print("[!] Backend slow — continuing anyway")
        time.sleep(2.0)

    print("[*] Opening JARVIS HUD...")
    try:
        window = webview.create_window(
            title="JARVIS",
            url=FRONTEND.as_uri(),
            width=1280,
            height=760,
            resizable=True,
            frameless=False,
            on_top=False,
            background_color="#050a0f",
        )

        # After window appears, find + save its HWND in background
        threading.Thread(target=find_and_save_hwnd, daemon=True).start()

        webview.start(debug=False)

    except Exception as e:
        print(f"[!] pywebview failed: {e} — falling back to browser")
        import webbrowser
        webbrowser.open(FRONTEND.as_uri())
        try:
            backend_proc.wait()
        except KeyboardInterrupt:
            pass

    print("\n[*] Shutting down JARVIS...")
    if HWND_FILE.exists():
        HWND_FILE.unlink()
    backend_proc.terminate()
