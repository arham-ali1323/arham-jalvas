"""The allowlist of actions a paired desktop may be asked to perform.

This module is the security boundary for web→desktop control. Nothing reaches a
paired computer unless it is described here, and every parameter is validated
against a strict schema before a command is ever queued.

Design rules (from the brief):

* **No arbitrary shell.** There is no "run command" action and there never will
  be. Every action maps to one concrete, curated operation on the desktop.
* **No unrestricted AI-generated commands.** The model — or the web UI, or an
  attacker holding a stolen session — can only pick a name from this list and
  fill in fields this module validates.
* **Sensitive actions require on-device confirmation.** Shutdown, restart, lock
  and sleep are marked `requires_confirmation`; the desktop refuses to run them
  until a human presses a button on that machine.
* **Scoped permissions.** Each action belongs to a permission scope that a user
  grants or revokes per device.

The desktop companion (`core/desktop_actions.py`) implements this same list; the
two are kept in step deliberately and a test asserts the names agree.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

# Permission scopes. A device is granted a subset of these on pairing.
PERMISSION_APP_LAUNCH = "app.launch"
PERMISSION_BROWSER = "browser.navigate"
PERMISSION_SYSTEM = "system.info"
PERMISSION_MEDIA = "media.control"
PERMISSION_VOLUME = "volume.control"
PERMISSION_NOTIFY = "notification.send"
PERMISSION_POWER = "power.control"

ALL_PERMISSIONS: tuple[str, ...] = (
    PERMISSION_APP_LAUNCH,
    PERMISSION_BROWSER,
    PERMISSION_SYSTEM,
    PERMISSION_MEDIA,
    PERMISSION_VOLUME,
    PERMISSION_NOTIFY,
    PERMISSION_POWER,
)


class ActionValidationError(ValueError):
    """Raised when a command names an unknown action or passes bad parameters.

    The message is safe to show a user — it never echoes raw input back in a way
    that could be used to probe the server.
    """


@dataclass(frozen=True)
class DeviceAction:
    name: str
    description: str
    permission: str
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
    requires_confirmation: bool = False
    # Whether this permission is granted by default when a device is paired.
    # Power control is opt-in; everything else is on unless the user turns it off.
    default_granted: bool = True

    def public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permission": self.permission,
            "parameters": self.parameters,
            "requires_confirmation": self.requires_confirmation,
            "default_granted": self.default_granted,
        }


# ── Parameter validators ──────────────────────────────────────────────────────
# Strict on purpose. Each returns the normalised value or raises.

_APP_RE = re.compile(r"^[A-Za-z0-9 ._+()\-]{1,80}$")
_TITLE_RE = re.compile(r"^.{1,120}$", re.DOTALL)


def _v_none(params: dict[str, Any]) -> dict[str, Any]:
    return {}


def _v_open_app(params: dict[str, Any]) -> dict[str, Any]:
    app = params.get("app")
    if not isinstance(app, str) or not _APP_RE.match(app.strip()):
        raise ActionValidationError("app must be a short application name.")
    return {"app": app.strip()}


def _v_navigate(params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url")
    if not isinstance(url, str):
        raise ActionValidationError("url is required.")
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ActionValidationError("url must be a valid http(s) address.")
    return {"url": url}


def _v_media(params: dict[str, Any]) -> dict[str, Any]:
    command = params.get("command")
    allowed = {"play_pause", "next", "previous", "stop"}
    if command not in allowed:
        raise ActionValidationError(
            f"command must be one of {sorted(allowed)}."
        )
    return {"command": command}


def _v_volume_set(params: dict[str, Any]) -> dict[str, Any]:
    level = params.get("level")
    if isinstance(level, bool) or not isinstance(level, (int, float)):
        raise ActionValidationError("level must be a number between 0 and 100.")
    level = int(level)
    if not 0 <= level <= 100:
        raise ActionValidationError("level must be between 0 and 100.")
    return {"level": level}


def _v_volume_mute(params: dict[str, Any]) -> dict[str, Any]:
    muted = params.get("muted")
    if not isinstance(muted, bool):
        raise ActionValidationError("muted must be true or false.")
    return {"muted": muted}


def _v_notify(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title")
    body = params.get("body", "")
    if not isinstance(title, str) or not _TITLE_RE.match(title):
        raise ActionValidationError("title must be 1–120 characters.")
    if not isinstance(body, str) or len(body) > 500:
        raise ActionValidationError("body must be at most 500 characters.")
    return {"title": title, "body": body}


_VALIDATORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "open_app": _v_open_app,
    "browser.navigate": _v_navigate,
    "system.info": _v_none,
    "media.control": _v_media,
    "volume.set": _v_volume_set,
    "volume.mute": _v_volume_mute,
    "notification.send": _v_notify,
    "screen.lock": _v_none,
    "power.sleep": _v_none,
    "power.shutdown": _v_none,
    "power.restart": _v_none,
}


def _empty() -> dict[str, dict[str, Any]]:
    return {}


def _p(**kw: Any) -> dict[str, dict[str, Any]]:
    return kw


ACTIONS: dict[str, DeviceAction] = {
    a.name: a
    for a in (
        DeviceAction(
            name="open_app",
            description="Launch an application by name.",
            permission=PERMISSION_APP_LAUNCH,
            parameters=_p(app={"type": "string", "description": "Application name"}),
        ),
        DeviceAction(
            name="browser.navigate",
            description="Open an http(s) URL in the default browser.",
            permission=PERMISSION_BROWSER,
            parameters=_p(url={"type": "string", "description": "http(s) URL"}),
        ),
        DeviceAction(
            name="system.info",
            description="Return CPU, memory and uptime for the machine.",
            permission=PERMISSION_SYSTEM,
            parameters=_empty(),
        ),
        DeviceAction(
            name="media.control",
            description="Control media playback.",
            permission=PERMISSION_MEDIA,
            parameters=_p(
                command={
                    "type": "string",
                    "enum": ["play_pause", "next", "previous", "stop"],
                }
            ),
        ),
        DeviceAction(
            name="volume.set",
            description="Set the system output volume (0–100).",
            permission=PERMISSION_VOLUME,
            parameters=_p(level={"type": "integer", "minimum": 0, "maximum": 100}),
        ),
        DeviceAction(
            name="volume.mute",
            description="Mute or unmute the system output.",
            permission=PERMISSION_VOLUME,
            parameters=_p(muted={"type": "boolean"}),
        ),
        DeviceAction(
            name="notification.send",
            description="Show a desktop notification.",
            permission=PERMISSION_NOTIFY,
            parameters=_p(
                title={"type": "string", "maxLength": 120},
                body={"type": "string", "maxLength": 500},
            ),
        ),
        DeviceAction(
            name="screen.lock",
            description="Lock the screen.",
            permission=PERMISSION_POWER,
            requires_confirmation=True,
            default_granted=False,
            parameters=_empty(),
        ),
        DeviceAction(
            name="power.sleep",
            description="Put the machine to sleep.",
            permission=PERMISSION_POWER,
            requires_confirmation=True,
            default_granted=False,
            parameters=_empty(),
        ),
        DeviceAction(
            name="power.shutdown",
            description="Shut the machine down.",
            permission=PERMISSION_POWER,
            requires_confirmation=True,
            default_granted=False,
            parameters=_empty(),
        ),
        DeviceAction(
            name="power.restart",
            description="Restart the machine.",
            permission=PERMISSION_POWER,
            requires_confirmation=True,
            default_granted=False,
            parameters=_empty(),
        ),
    )
}


# Which declared parameters are mandatory (all declared params are required
# unless listed as optional here).
_OPTIONAL: dict[str, set[str]] = {
    "open_app": set(),
    "browser.navigate": set(),
    "system.info": set(),
    "media.control": set(),
    "volume.set": set(),
    "volume.mute": set(),
    "notification.send": {"body"},
    "screen.lock": set(),
    "power.sleep": set(),
    "power.shutdown": set(),
    "power.restart": set(),
}
_REQUIRED: dict[str, set[str]] = {
    name: set(a.parameters) - _OPTIONAL.get(name, set())
    for name, a in ACTIONS.items()
}


def default_permissions() -> list[str]:
    """The permission scopes granted to a freshly paired device."""
    return sorted(
        {a.permission for a in ACTIONS.values() if a.default_granted}
    )


def get_action(name: str) -> DeviceAction:
    action = ACTIONS.get(name)
    if action is None:
        raise ActionValidationError(f"Unknown action '{name}'.")
    return action


def validate(name: str, parameters: dict[str, Any] | None) -> dict[str, Any]:
    """Validate an action name + parameters and return the normalised params.

    Raises `ActionValidationError` for anything not on the allowlist or with a
    parameter that fails its schema.
    """
    action = get_action(name)
    params = parameters or {}
    if not isinstance(params, dict):
        raise ActionValidationError("parameters must be an object.")
    # Reject unexpected keys so a client cannot smuggle extra data through.
    unknown = set(params) - set(action.parameters)
    if unknown:
        raise ActionValidationError(
            f"Unexpected parameter(s): {', '.join(sorted(unknown))}."
        )
    required = _REQUIRED.get(name, set(action.parameters))
    missing = required - set(params)
    if missing:
        raise ActionValidationError(
            f"Missing parameter(s): {', '.join(sorted(missing))}."
        )
    return _VALIDATORS[name](params)
