import subprocess
import platform
import os
import time
import glob
import ctypes
import ctypes.wintypes
import psutil
import pyautogui
import shutil
from pathlib import Path
from datetime import datetime

SYSTEM = platform.system()

# ── App map ───────────────────────────────────────────────────────────────────
WIN_APP_MAP = {
    "chrome":       [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")],
    "firefox":      [r"C:\Program Files\Mozilla Firefox\firefox.exe", r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"],
    "discord":      [os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe"), os.path.expandvars(r"%LOCALAPPDATA%\Discord\app-*\Discord.exe")],
    "sklauncher":   [os.path.expandvars(r"%USERPROFILE%\Downloads\SKlauncher*.exe"), os.path.expandvars(r"%USERPROFILE%\Desktop\SKlauncher*.exe"), r"C:\Program Files\SKlauncher\SKlauncher.exe"],
    "minecraft":    [r"C:\Program Files (x86)\Minecraft Launcher\MinecraftLauncher.exe", r"C:\Program Files\Minecraft Launcher\MinecraftLauncher.exe"],
    "notepad":      ["notepad.exe"],
    "notepad++":    [r"C:\Program Files\Notepad++\notepad++.exe", r"C:\Program Files (x86)\Notepad++\notepad++.exe"],
    "vs code":      [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe")],
    "vscode":       [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe")],
    "steam":        [r"C:\Program Files (x86)\Steam\steam.exe", r"C:\Program Files\Steam\steam.exe"],
    "spotify":      [os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")],
    "vlc":          [r"C:\Program Files\VideoLAN\VLC\vlc.exe", r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"],
    "explorer":     ["explorer.exe"],
    "file manager": ["explorer.exe"],
    "calculator":   ["calc.exe"],
    "task manager": ["taskmgr.exe"],
    "terminal":     ["cmd.exe"],
    "cmd":          ["cmd.exe"],
    "powershell":   ["powershell.exe"],
    "paint":        ["mspaint.exe"],
    "wordpad":      ["wordpad.exe"],
    "settings":     ["ms-settings:"],
    "control panel":["control.exe"],
    "wifi settings":["ms-settings:network-wifi"],
    "bluetooth":    ["ms-settings:bluetooth"],
    "display settings": ["ms-settings:display"],
    "sound settings":   ["ms-settings:sound"],
    "privacy settings": ["ms-settings:privacy"],
    "windows update":   ["ms-settings:windowsupdate"],
}

URL_MAP = {
    "youtube": "https://youtube.com",
    "google":  "https://google.com",
    "github":  "https://github.com",
    "reddit":  "https://reddit.com",
    "twitter": "https://twitter.com",
    "x":       "https://x.com",
    "roblox":  "https://roblox.com",
    "gmail":   "https://mail.google.com",
    "maps":    "https://maps.google.com",
}

def _resolve_path(candidates):
    for p in candidates:
        if "*" in p:
            matches = glob.glob(p)
            if matches:
                return sorted(matches)[-1]
        elif os.path.exists(p):
            return p
    return None

def _focus_window_by_title(keyword: str):
    try:
        user32 = ctypes.windll.user32
        found = [None]
        kw = keyword.lower()
        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n > 0:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    if kw in buf.value.lower():
                        found[0] = hwnd
                        return False
            return True
        user32.EnumWindows(cb, 0)
        if found[0]:
            user32.ShowWindow(found[0], 9)
            user32.SetForegroundWindow(found[0])
            return True
    except:
        pass
    return False

def open_app(name: str) -> str:
    n = name.lower().strip()

    if n.startswith("http://") or n.startswith("https://"):
        import webbrowser; webbrowser.open(n)
        return f"Opened {n} in browser."

    for key, url in URL_MAP.items():
        if key in n:
            import webbrowser; webbrowser.open(url)
            return f"Opened {key} in browser."

    # ms-settings shortcuts
    for key, val in WIN_APP_MAP.items():
        if key in n:
            if isinstance(val, list) and val[0].startswith("ms-settings:"):
                subprocess.Popen(["start", val[0]], shell=True)
                return f"Opened {key}."
            exe = _resolve_path(val)
            if exe:
                try:
                    if "discord" in key:
                        subprocess.Popen([exe, "--processStart", "Discord.exe"])
                    else:
                        subprocess.Popen([exe], shell=False)
                    time.sleep(1.5)
                    _focus_window_by_title(key)
                    return f"Opening {key}."
                except Exception as e:
                    return f"Found {key} but failed to launch: {e}"
            else:
                return f"Can't find {key} installed. Add its path to WIN_APP_MAP."

    # Smart search: look for exe by name across common dirs
    search_dirs = [
        r"C:\Program Files", r"C:\Program Files (x86)",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
        os.path.expandvars(r"%APPDATA%"),
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        os.path.expandvars(r"%USERPROFILE%\Downloads"),
    ]
    term = n.replace(" ", "*")
    for d in search_dirs:
        matches = glob.glob(os.path.join(d, "**", f"*{term}*.exe"), recursive=True)
        if matches:
            exe = matches[0]
            subprocess.Popen([exe])
            time.sleep(1.5)
            _focus_window_by_title(n)
            return f"Found and launched {os.path.basename(exe)}."

    try:
        subprocess.Popen(name, shell=True)
        return f"Trying to run '{name}'."
    except:
        return f"Couldn't find or open '{name}'."

# ── File system operations ────────────────────────────────────────────────────
def list_files(path: str = None) -> dict:
    """List files and folders in a directory."""
    target = Path(path) if path else Path.home()
    try:
        items = []
        for item in sorted(target.iterdir()):
            try:
                stat = item.stat()
                items.append({
                    "name": item.name,
                    "type": "folder" if item.is_dir() else "file",
                    "size": stat.st_size if item.is_file() else None,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "path": str(item),
                })
            except PermissionError:
                items.append({"name": item.name, "type": "unknown", "path": str(item)})
        return {"path": str(target), "items": items, "count": len(items)}
    except PermissionError:
        return {"error": f"Permission denied: {target}"}
    except Exception as e:
        return {"error": str(e)}

def read_file(path: str) -> dict:
    """Read a text file."""
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"File not found: {path}"}
        if p.stat().st_size > 500_000:
            return {"error": "File too large (>500KB). Use a text editor."}
        content = p.read_text(encoding="utf-8", errors="replace")
        return {"path": str(p), "content": content, "lines": content.count("\n") + 1}
    except Exception as e:
        return {"error": str(e)}

def write_file(path: str, content: str) -> dict:
    """Write/overwrite a text file."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(p), "bytes": len(content.encode())}
    except Exception as e:
        return {"error": str(e)}

def delete_file(path: str) -> dict:
    """Delete a file or folder (moves to recycle bin via shell)."""
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"Not found: {path}"}
        # Use shell delete (recycle bin) for safety
        import winreg
        shell32 = ctypes.windll.shell32
        # SHFileOperation — move to recycle bin (FOF_ALLOWUNDO=0x40, FOF_NOCONFIRMATION=0x10)
        result = shell32.SHFileOperationW(ctypes.byref(_make_shfileopstruct(str(p))))
        return {"ok": True, "path": str(p), "note": "Moved to recycle bin."}
    except Exception as e:
        # fallback
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            return {"ok": True, "path": str(p)}
        except Exception as e2:
            return {"error": str(e2)}

def _make_shfileopstruct(path):
    import ctypes
    class SHFILEOPSTRUCT(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.wintypes.HWND),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]
    op = SHFILEOPSTRUCT()
    op.wFunc = 3  # FO_DELETE
    op.pFrom = path + "\0\0"
    op.fFlags = 0x40 | 0x10  # FOF_ALLOWUNDO | FOF_NOCONFIRMATION
    return op

def search_files(query: str, search_path: str = None) -> dict:
    """Search for files matching a name pattern."""
    base = Path(search_path) if search_path else Path.home()
    try:
        matches = []
        for p in base.rglob(f"*{query}*"):
            try:
                matches.append({"name": p.name, "path": str(p), "type": "folder" if p.is_dir() else "file"})
                if len(matches) >= 30:
                    break
            except:
                pass
        return {"query": query, "results": matches, "count": len(matches)}
    except Exception as e:
        return {"error": str(e)}

def open_file(path: str) -> dict:
    """Open a file with its default application."""
    try:
        os.startfile(path)
        return {"ok": True, "path": path}
    except Exception as e:
        return {"error": str(e)}

def run_command(cmd: str) -> dict:
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return {
            "command": cmd,
            "stdout": result.stdout.strip()[:2000],
            "stderr": result.stderr.strip()[:500],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out (15s limit)."}
    except Exception as e:
        return {"error": str(e)}

# ── Discord messaging via pyautogui ──────────────────────────────────────────
def discord_send_message(message: str, channel_name: str = None) -> dict:
    """Focus Discord and send a message. Optionally search for a channel first."""
    try:
        # Focus Discord
        if not _focus_window_by_title("discord"):
            open_app("discord")
            time.sleep(3)
            _focus_window_by_title("discord")

        time.sleep(0.5)

        if channel_name:
            # Ctrl+K to open quick switcher
            pyautogui.hotkey("ctrl", "k")
            time.sleep(0.4)
            pyautogui.typewrite(channel_name, interval=0.05)
            time.sleep(0.6)
            pyautogui.press("enter")
            time.sleep(0.5)

        # Click message box area (Discord's input is at bottom)
        pyautogui.hotkey("alt", "shift", "i")  # focus message input shortcut
        time.sleep(0.3)
        # Fallback: just type (Discord auto-focuses input in most cases)
        pyautogui.typewrite(message, interval=0.04)
        time.sleep(0.2)
        pyautogui.press("enter")
        return {"ok": True, "message": message, "channel": channel_name}
    except Exception as e:
        return {"error": str(e)}

# ── System awareness ──────────────────────────────────────────────────────────
def get_open_windows() -> list:
    """Get list of currently open/visible windows."""
    user32 = ctypes.windll.user32
    windows = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 2:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value.strip()
                if title and title not in windows:
                    windows.append(title)
        return True
    user32.EnumWindows(cb, 0)
    return windows[:20]

def get_clipboard() -> str:
    """Get current clipboard text."""
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        text = r.clipboard_get()
        r.destroy()
        return text[:500]
    except:
        return ""

def get_active_window_title() -> str:
    """Get the title of the currently focused window."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
    except:
        return "Unknown"

def get_running_processes() -> list:
    """Get top 10 CPU-using processes."""
    procs = []
    for p in sorted(psutil.process_iter(['name', 'cpu_percent', 'memory_percent']),
                    key=lambda x: x.info.get('cpu_percent', 0) or 0, reverse=True)[:10]:
        try:
            procs.append({
                "name": p.info['name'],
                "cpu": round(p.info.get('cpu_percent', 0) or 0, 1),
                "mem": round(p.info.get('memory_percent', 0) or 0, 1),
            })
        except:
            pass
    return procs

def get_full_context() -> dict:
    """Return full system context for AI awareness."""
    return {
        "active_window": get_active_window_title(),
        "open_windows": get_open_windows(),
        "clipboard": get_clipboard(),
        "processes": get_running_processes(),
        "time": datetime.now().strftime("%I:%M %p, %A %B %d %Y"),
        "username": os.environ.get("USERNAME", "User"),
        "desktop": str(Path.home() / "Desktop"),
        "downloads": str(Path.home() / "Downloads"),
        "documents": str(Path.home() / "Documents"),
    }

# ── Type text / keyboard ──────────────────────────────────────────────────────
def type_text(text: str) -> str:
    try:
        time.sleep(0.5)
        pyautogui.typewrite(text, interval=0.04)
        return f"Typed: {text}"
    except Exception as e:
        return f"Couldn't type: {e}"





def _gb(b): return f"{round(b/1e9,1)} GB"
