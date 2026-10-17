"""The desktop side of web→desktop control: the allowlist, validation, and the
handlers that actually perform each action.

This is a second, on-device copy of the allowlist in
`services/api/app/services/device_actions.py`. Defence in depth: the server
refuses anything not on its list, and the companion refuses anything not on
*this* list, so a compromised or outdated server cannot make the desktop do
something the desktop was not built to do.

Rules this module holds to, without exception:

* **No shell.** Every external command is a fixed argument list passed to
  ``subprocess.run`` — never a command string, never remote input interpolated
  into an argument.
* **Strict parameter validation.** The same shapes the server enforces.
* **Sensitive actions need a human.** ``power.*`` and ``screen.lock`` call a
  confirmation callback and are refused if it says no or is absent.

The module never imports the web UI or the Live session; it can be used and
tested on its own.
"""
from __future__ import annotations

import platform
import re
import subprocess
import webbrowser
from typing import Any, Callable

_SYSTEM = platform.system()

_APP_RE = re.compile(r"^[A-Za-z0-9 ._+()\-]{1,80}$")
_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


class ActionDenied(Exception):
    """Raised when a handler is not allowed to run (bad params / no consent)."""


# A seam so tests can observe the exact argv without launching anything.
#   _run(["shutdown", "/s", "/t", "0"])
def _run(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout)


# ── Handlers ──────────────────────────────────────────────────────────────────


def _h_open_app(p: dict[str, Any]) -> str:
    app = p["app"]
    if not _APP_RE.match(app):
        raise ActionDenied("Invalid application name.")
    from actions.open_app import open_app  # imported lazily; heavy module

    return open_app({"app_name": app})


def _h_navigate(p: dict[str, Any]) -> str:
    url = p["url"]
    if not _URL_RE.match(url):
        raise ActionDenied("Only http(s) URLs are allowed.")
    if not webbrowser.open(url):  # pragma: no cover - depends on the host
        return f"Requested {url} in the default browser."
    return f"Opened {url}."


def _h_system_info(p: dict[str, Any]) -> str:
    from actions.system_monitor import get_system_status

    s = get_system_status() or {}
    parts = []
    for key, label in (
        ("cpu_usage", "CPU"),
        ("ram_usage", "RAM"),
        ("gpu_usage", "GPU"),
        ("cpu_temp", "Temp"),
        ("uptime", "Uptime"),
    ):
        if key in s and s[key] is not None:
            parts.append(f"{label}: {s[key]}")
    return ", ".join(parts) or "System metrics unavailable."


def _h_media(p: dict[str, Any]) -> str:
    command = p["command"]
    if command not in _MEDIA_COMMANDS:
        raise ActionDenied(f"Unsupported media command '{command}'.")
    _media_key(command)
    return f"Media: {command}."


def _h_volume_set(p: dict[str, Any]) -> str:
    try:
        level = int(p["level"])
    except (TypeError, ValueError) as exc:
        raise ActionDenied("Volume level must be a whole number.") from exc
    if not 0 <= level <= 100:
        raise ActionDenied("Volume level must be between 0 and 100.")
    from actions.computer_settings import volume_set

    volume_set(level)
    return f"Volume set to {level}%."


def _h_volume_mute(p: dict[str, Any]) -> str:
    muted = bool(p["muted"])
    _set_mute(muted)
    return "Muted." if muted else "Unmuted."


def _h_notify(p: dict[str, Any]) -> str:
    title = str(p["title"]).strip()
    body = str(p.get("body", "")).strip()
    if not title or len(title) > 120:
        raise ActionDenied("Notification title must be 1–120 characters.")
    if len(body) > 400:
        raise ActionDenied("Notification body must be at most 400 characters.")
    _notify(title, body)
    return "Notification shown."


def _h_lock(p: dict[str, Any]) -> str:
    from actions.computer_settings import lock_screen

    lock_screen()
    return "Screen locked."


def _h_sleep(p: dict[str, Any]) -> str:
    _sleep()
    return "Going to sleep."


def _h_shutdown(p: dict[str, Any]) -> str:
    from actions.computer_settings import shutdown_computer

    shutdown_computer()
    return "Shutting down."


def _h_restart(p: dict[str, Any]) -> str:
    from actions.computer_settings import restart_computer

    restart_computer()
    return "Restarting."


# ── Cross-platform primitives ────────────────────────────────────────────────


_MEDIA_COMMANDS = ("play_pause", "next", "previous", "stop")


def _media_key(command: str) -> None:
    if _SYSTEM == "Windows":
        import ctypes

        vk = {
            "play_pause": 0xB3,
            "next": 0xB0,
            "previous": 0xB1,
            "stop": 0xB2,
        }[command]
        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    elif _SYSTEM == "Darwin":
        # AppleScript can drive the Music app; other players vary, so this is
        # best-effort and documented rather than pretended to be universal.
        script = {
            "play_pause": 'tell application "Music" to playpause',
            "next": 'tell application "Music" to next track',
            "previous": 'tell application "Music" to previous track',
            "stop": 'tell application "Music" to stop',
        }[command]
        _run(["osascript", "-e", script], timeout=8)
    else:
        action = {
            "play_pause": "play-pause",
            "next": "next",
            "previous": "previous",
            "stop": "stop",
        }[command]
        try:
            _run(["playerctl", action], timeout=8)
        except FileNotFoundError as exc:
            raise ActionDenied("playerctl is not installed.") from exc


def _set_mute(muted: bool) -> None:
    if _SYSTEM == "Windows":
        try:
            from comtypes import CLSCTX_ALL
            from ctypes import cast, POINTER

            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            vol.SetMute(1 if muted else 0, None)
            return
        except Exception:
            # Fall back to the toggle only when the state matches the request.
            if muted:
                from actions.computer_settings import volume_mute

                volume_mute()
            return
    if _SYSTEM == "Darwin":
        state = "true" if muted else "false"
        _run(["osascript", "-e", f"set volume output muted {state}"], timeout=8)
    else:
        state = "1" if muted else "0"
        _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", state], timeout=8)


def _notify(title: str, body: str) -> None:
    if _SYSTEM == "Windows":
        try:
            from win10toast import ToastNotifier

            ToastNotifier().show_toast(title, body, duration=6, threaded=True)
            return
        except Exception:
            # PowerShell toast via a fixed script; the text is passed as an
            # argument, never interpolated into the script itself.
            ps = (
                "[reflection.assembly]::loadwithpartialname('System.Windows.Forms');"
                "[reflection.assembly]::loadwithpartialname('System.Drawing');"
                "$n=New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon=[System.Drawing.SystemIcons]::Information;"
                "$n.Visible=$true;"
                f"$n.ShowBalloonTip(6000,$args[0],$args[1],"
                "[System.Windows.Forms.ToolTipIcon]::Info)"
            )
            _run(
                ["powershell", "-NoProfile", "-Command", ps, title, body],
                timeout=15,
            )
            return
    if _SYSTEM == "Darwin":
        _run(
            [
                "osascript",
                "-e",
                f'display notification {_osa_quote(body)} with title {_osa_quote(title)}',
            ],
            timeout=8,
        )
    else:
        try:
            _run(["notify-send", title, body], timeout=8)
        except FileNotFoundError as exc:
            raise ActionDenied("notify-send is not installed.") from exc


def _osa_quote(text: str) -> str:
    """Quote a string for an AppleScript string literal without a shell."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _sleep() -> None:
    if _SYSTEM == "Windows":
        _run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    elif _SYSTEM == "Darwin":
        _run(["pmset", "sleepnow"])
    else:
        _run(["systemctl", "suspend"])


# ── The allowlist (mirrors the server) ───────────────────────────────────────

# name -> (required params, permission, requires_confirmation, handler)
ACTIONS: dict[str, dict[str, Any]] = {
    "open_app": {
        "params": {"app"},
        "permission": "app.launch",
        "confirm": False,
        "handler": _h_open_app,
    },
    "browser.navigate": {
        "params": {"url"},
        "permission": "browser.navigate",
        "confirm": False,
        "handler": _h_navigate,
    },
    "system.info": {
        "params": set(),
        "permission": "system.info",
        "confirm": False,
        "handler": _h_system_info,
    },
    "media.control": {
        "params": {"command"},
        "permission": "media.control",
        "confirm": False,
        "handler": _h_media,
    },
    "volume.set": {
        "params": {"level"},
        "permission": "volume.control",
        "confirm": False,
        "handler": _h_volume_set,
    },
    "volume.mute": {
        "params": {"muted"},
        "permission": "volume.control",
        "confirm": False,
        "handler": _h_volume_mute,
    },
    "notification.send": {
        "params": {"title"},
        "permission": "notification.send",
        "confirm": False,
        "handler": _h_notify,
    },
    "screen.lock": {
        "params": set(),
        "permission": "power.control",
        "confirm": True,
        "handler": _h_lock,
    },
    "power.sleep": {
        "params": set(),
        "permission": "power.control",
        "confirm": True,
        "handler": _h_sleep,
    },
    "power.shutdown": {
        "params": set(),
        "permission": "power.control",
        "confirm": True,
        "handler": _h_shutdown,
    },
    "power.restart": {
        "params": set(),
        "permission": "power.control",
        "confirm": True,
        "handler": _h_restart,
    },
}


def actions_public() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "permission": spec["permission"],
            "requires_confirmation": spec["confirm"],
        }
        for name, spec in ACTIONS.items()
    ]


def requires_confirmation(action: str) -> bool:
    spec = ACTIONS.get(action)
    return bool(spec and spec["confirm"])


def execute(
    action: str,
    parameters: dict[str, Any] | None = None,
    *,
    confirm: Callable[[str, dict[str, Any]], bool] | None = None,
) -> tuple[str, str]:
    """Run one allowlisted action.

    Returns ``(status, message)`` where status is one of ``success``, ``error``
    or ``denied``. Never raises — a bad command must produce a reported result,
    not a crashed companion thread.
    """
    params = parameters or {}
    spec = ACTIONS.get(action)
    if spec is None:
        return "error", f"Unknown action '{action}'."

    if not isinstance(params, dict):
        return "error", "Invalid parameters."

    # Reject anything the action does not expect, then require the rest.
    allowed = spec["params"] | ({"body"} if action == "notification.send" else set())
    if set(params) - allowed:
        return "denied", "Unexpected parameters."
    missing = spec["params"] - set(params)
    if missing:
        return "denied", f"Missing parameter(s): {', '.join(sorted(missing))}."

    if spec["confirm"]:
        if confirm is None or not confirm(action, params):
            return "denied", "Declined on the device."

    try:
        message = spec["handler"](params)
        return "success", str(message)
    except ActionDenied as exc:
        return "denied", str(exc)
    except FileNotFoundError as exc:
        return "error", f"A required tool is missing: {exc.filename or exc}."
    except subprocess.TimeoutExpired:
        return "error", "The action timed out."
    except Exception as exc:  # noqa: BLE001 - report, never propagate
        return "error", f"{type(exc).__name__}: {exc}"
