"""
groq_client.py  –  JARVIS backend
Capabilities:
  • Open / close applications
  • Run any shell command
  • File & folder operations  (create, read, write, delete, list)
  • Keyboard / mouse control  (type, hotkey, click, scroll)
  • Take screenshots
  • Web search  (DuckDuckGo, no API key)
  • Get clipboard / set clipboard
  • System info  (battery, volume, processes, …)
"""

import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

from groq import Groq

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False

try:
    import pyperclip
    PYPERCLIP_OK = True
except ImportError:
    PYPERCLIP_OK = False

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

# ───────────────────────────── config ──────────────────────────────
KEY_FILE = Path(__file__).parent / "api.txt"
OS_NAME  = platform.system()
USERNAME = os.getlogin()

SYSTEM_PROMPT = f"""You are JARVIS, a sharp AI assistant with FULL CONTROL over the user's PC.
OS: {OS_NAME} | User: {USERNAME}

Rules you must ALWAYS follow:
- Respond in plain text only. No markdown, no bullet points, no asterisks.
- Keep replies under 3 sentences unless asked for more detail.
- Be direct, intelligent, slightly dry in tone.
- When the user asks you to DO something (open app, create file, search web, run command, type text),
  you MUST call the correct tool. Never say you did something without calling the tool.
- After a tool runs, confirm briefly what happened in plain text.
- Never call a tool again if you already have the result. Just reply.
"""

# ────────────────────────── tool definitions ───────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Execute any shell command on the user's PC and return its output. "
                "Use for opening apps (e.g. 'start discord'), system tasks, scripts, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Max seconds to wait. Default 10.",
                        "default": 10
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_op",
            "description": "Create, read, write, append, delete, list, copy, or move files and folders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "read", "write", "append", "delete", "list", "copy", "move", "mkdir"]
                    },
                    "path": {
                        "type": "string",
                        "description": "Target file or folder path"
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content (for write / append / create)"
                    },
                    "dest": {
                        "type": "string",
                        "description": "Destination path (for copy / move)"
                    }
                },
                "required": ["action", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web via DuckDuckGo. Returns titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return. Default 5.",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "keyboard_mouse",
            "description": "Control keyboard and mouse: type text, press hotkeys, click, scroll, screenshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["type", "hotkey", "press", "click", "right_click",
                                 "double_click", "move", "scroll", "screenshot"]
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type, or comma-separated key names for hotkey e.g. 'ctrl,c'"
                    },
                    "x": {"type": "integer", "description": "Screen X coordinate"},
                    "y": {"type": "integer", "description": "Screen Y coordinate"},
                    "clicks": {"type": "integer", "description": "Scroll amount (positive = up)"},
                    "save_to": {"type": "string", "description": "File path to save screenshot"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard",
            "description": "Get or set the system clipboard text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get", "set"]
                    },
                    "content": {
                        "type": "string",
                        "description": "Text to copy to clipboard (only for action=set)"
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "system_info",
            "description": "Get system info: battery, running processes, CPU/RAM, disk, or network usage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "enum": ["battery", "processes", "cpu_ram", "disk", "network"]
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# ──────────────────────────── tool handlers ────────────────────────

def _run_shell(command: str, timeout: int = 10) -> str:
    try:
        if OS_NAME == "Windows" and command.strip().lower().startswith("start "):
            os.system(command)
            return f"Launched: {command}"
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout,
            **({"executable": "/bin/bash"} if OS_NAME != "Windows" else {})
        )
        out = (result.stdout + result.stderr).strip()
        return out[:1500] if out else "(completed with no output)"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s — process may still be running."
    except Exception as e:
        return f"Shell error: {e}"


def _file_op(action: str, path: str, content: str = "", dest: str = "") -> str:
    p = Path(path).expanduser()
    try:
        if action == "create":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Created: {p}"
        elif action == "read":
            if not p.exists():
                return f"File not found: {p}"
            return p.read_text(encoding="utf-8", errors="replace")[:3000]
        elif action == "write":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Written: {p}"
        elif action == "append":
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(content)
            return f"Appended to: {p}"
        elif action == "delete":
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink(missing_ok=True)
            return f"Deleted: {p}"
        elif action == "list":
            if not p.exists():
                return f"Path not found: {p}"
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            return "\n".join(
                ("[DIR]  " if i.is_dir() else "[FILE] ") + i.name for i in items
            ) or "(empty directory)"
        elif action == "copy":
            shutil.copy2(str(p), dest)
            return f"Copied {p} -> {dest}"
        elif action == "move":
            shutil.move(str(p), dest)
            return f"Moved {p} -> {dest}"
        elif action == "mkdir":
            p.mkdir(parents=True, exist_ok=True)
            return f"Directory created: {p}"
        else:
            return f"Unknown file action: {action}"
    except Exception as e:
        return f"File error: {e}"


def _web_search(query: str, num_results: int = 5) -> str:
    if not REQUESTS_OK:
        return "requests / beautifulsoup4 not installed. Run: pip install requests beautifulsoup4"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    try:
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for res in soup.select(".result")[:num_results]:
            title_el = res.select_one(".result__title")
            url_el   = res.select_one(".result__url")
            snip_el  = res.select_one(".result__snippet")
            title   = title_el.get_text(strip=True) if title_el else "No title"
            href    = url_el.get_text(strip=True)   if url_el   else ""
            snippet = snip_el.get_text(strip=True)  if snip_el  else ""
            results.append(f"- {title} | {href} | {snippet}")
        return "\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Search error: {e}"


def _keyboard_mouse(action: str, text: str = "", x: int = 0, y: int = 0,
                    clicks: int = 3, save_to: str = "") -> str:
    if not PYAUTOGUI_OK:
        return "pyautogui not installed. Run: pip install pyautogui"
    try:
        time.sleep(0.3)
        if action == "type":
            pyautogui.write(text, interval=0.04)
            return f"Typed: {text[:60]}"
        elif action == "hotkey":
            keys = [k.strip() for k in text.split(",")]
            pyautogui.hotkey(*keys)
            return f"Hotkey: {'+'.join(keys)}"
        elif action == "press":
            pyautogui.press(text)
            return f"Pressed: {text}"
        elif action == "click":
            pyautogui.click(x, y)
            return f"Clicked at ({x}, {y})"
        elif action == "right_click":
            pyautogui.rightClick(x, y)
            return f"Right-clicked at ({x}, {y})"
        elif action == "double_click":
            pyautogui.doubleClick(x, y)
            return f"Double-clicked at ({x}, {y})"
        elif action == "move":
            pyautogui.moveTo(x, y, duration=0.3)
            return f"Moved mouse to ({x}, {y})"
        elif action == "scroll":
            pyautogui.scroll(clicks)
            return f"Scrolled {clicks} units"
        elif action == "screenshot":
            path = save_to or str(Path.home() / "Desktop" / "jarvis_screenshot.png")
            pyautogui.screenshot(path)
            return f"Screenshot saved to {path}"
        else:
            return f"Unknown action: {action}"
    except Exception as e:
        return f"keyboard_mouse error: {e}"


def _clipboard(action: str, content: str = "") -> str:
    if not PYPERCLIP_OK:
        return "pyperclip not installed. Run: pip install pyperclip"
    try:
        if action == "get":
            return pyperclip.paste() or "(clipboard is empty)"
        else:
            pyperclip.copy(content)
            return "Copied to clipboard."
    except Exception as e:
        return f"Clipboard error: {e}"


def _system_info(query: str) -> str:
    if not PSUTIL_OK:
        return "psutil not installed. Run: pip install psutil"
    try:
        if query == "battery":
            b = psutil.sensors_battery()
            if not b:
                return "No battery detected."
            return f"Battery: {b.percent:.0f}% - {'charging' if b.power_plugged else 'discharging'}"
        elif query == "processes":
            procs = sorted(
                psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]),
                key=lambda p: p.info["cpu_percent"] or 0, reverse=True
            )
            lines = [
                f"{p.info['name'][:28]:<28} PID={p.info['pid']}  "
                f"CPU={p.info['cpu_percent']}%  "
                f"RAM={p.info['memory_info'].rss // 1024 // 1024}MB"
                for p in procs[:15] if p.info["name"]
            ]
            return "\n".join(lines)
        elif query == "cpu_ram":
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory()
            return (
                f"CPU: {cpu}%  |  "
                f"RAM: {ram.used // 1024 // 1024}MB / {ram.total // 1024 // 1024}MB ({ram.percent}%)"
            )
        elif query == "disk":
            lines = []
            for part in psutil.disk_partitions():
                try:
                    u = psutil.disk_usage(part.mountpoint)
                    lines.append(
                        f"{part.device}  "
                        f"{u.used // 1024 // 1024 // 1024}GB / {u.total // 1024 // 1024 // 1024}GB "
                        f"({u.percent}%)"
                    )
                except Exception:
                    pass
            return "\n".join(lines)
        elif query == "network":
            s = psutil.net_io_counters()
            return f"Sent: {s.bytes_sent // 1024 // 1024}MB  |  Received: {s.bytes_recv // 1024 // 1024}MB"
    except Exception as e:
        return f"System info error: {e}"


# ── tool name -> handler ───────────────────────────────────────────
TOOL_HANDLERS = {
    "run_shell":      lambda args: _run_shell(**args),
    "file_op":        lambda args: _file_op(**args),
    "web_search":     lambda args: _web_search(**args),
    "keyboard_mouse": lambda args: _keyboard_mouse(**args),
    "clipboard":      lambda args: _clipboard(**args),
    "system_info":    lambda args: _system_info(**args),
}

# ─────────────────────────── Groq client ──────────────────────────
conversation_history: list[dict] = []
_client: Groq = None


def load_key() -> str | None:
    if not KEY_FILE.exists():
        print(f"[!] api.txt not found at {KEY_FILE}")
        return None
    key = KEY_FILE.read_text().strip()
    if not key:
        print("[!] api.txt is empty")
        return None
    if not key.startswith("gsk_"):
        print("[!] api.txt does not contain a valid Groq key (must start with gsk_)")
        return None
    print(f"[OK] Groq API key loaded  ({len(key)} chars)")
    return key


def init_client():
    global _client
    key = load_key()
    if not key:
        raise ValueError("No valid Groq API key in backend/api.txt")
    _client = Groq(api_key=key, timeout=30.0)


def _execute_tool_calls(tool_calls) -> list[dict]:
    """Execute every tool call; return list of tool-result messages."""
    results = []
    for tc in tool_calls:
        fn_name = tc.function.name
        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            args = {}

        print(f"  [TOOL] {fn_name}({args})")
        handler = TOOL_HANDLERS.get(fn_name)
        output = handler(args) if handler else f"Unknown tool: {fn_name}"
        print(f"  [RESULT] {str(output)[:120]}")

        results.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": str(output),
        })
    return results


def ask_groq(prompt: str) -> str:
    global _client
    if _client is None:
        init_client()

    conversation_history.append({"role": "user", "content": prompt})

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *conversation_history[-20:],
    ]

    try:
        # ── Round 1: initial call with tools enabled ──────────────────
        response = _client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1024,
            temperature=0.4,
            tools=TOOLS,
            tool_choice="auto",
            messages=messages,
        )
        msg = response.choices[0].message

        # ── Agentic loop ──────────────────────────────────────────────
        MAX_ROUNDS = 5
        for round_num in range(MAX_ROUNDS):
            if not msg.tool_calls:
                break

            # Append assistant tool-call message
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Execute tools and append results
            tool_results = _execute_tool_calls(msg.tool_calls)
            messages.extend(tool_results)

            # KEY FIX: force tool_choice="none" on last round so model
            # must produce a plain-text reply instead of calling more tools.
            # This prevents the Groq 400 "tool_use_failed" error.
            is_last_round = (round_num == MAX_ROUNDS - 1)
            response = _client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=512,
                temperature=0.4,
                tools=TOOLS,
                tool_choice="none" if is_last_round else "auto",
                messages=messages,
            )
            msg = response.choices[0].message

        # Safety net: if model still wants tools after MAX_ROUNDS,
        # do one final call with no tools at all to get a plain reply.
        if msg.tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })
            tool_results = _execute_tool_calls(msg.tool_calls)
            messages.extend(tool_results)
            response = _client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=512,
                temperature=0.4,
                messages=messages,  # no tools param = model can only reply
            )
            msg = response.choices[0].message

        reply = (msg.content or "Done.").strip()
        conversation_history.append({"role": "assistant", "content": reply})
        return reply

    except Exception as e:
        err = str(e)
        if "401" in err or "invalid api key" in err.lower():
            return "Error: Invalid Groq key in api.txt."
        return f"Groq error: {err[:250]}"


def clear_history():
    global conversation_history
    conversation_history = []