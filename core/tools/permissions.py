"""
Permissions for MARK LIV tools.

Defines the permissions a tool can require, a registry of which tools require
which permissions, and an approval gate for actions that may modify the project
or the assistant itself.

Read-only diagnostics (internet, DNS, news provider, service status) are
granted by default — they only observe and never change anything. Anything that
writes a file, changes a setting, or alters the tool registry requires explicit
approval through the approval gate, which the UI (or the operator) must wire in.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

# Permission names.
PERM_DIAGNOSTIC_READ = "diagnostic.read"   # observe system / network state
PERM_NEWS_READ       = "news.read"         # fetch public headlines
PERM_SYSTEM_READ     = "system.read"       # read local system metrics
PERM_DEV_DIAGNOSE    = "dev.diagnose"      # run development diagnostics
PERM_DEV_MODIFY      = "dev.modify"        # modify project files (approval only)

# Permissions that are safe to grant without asking the user.
_SAFE_DEFAULTS = {
    PERM_DIAGNOSTIC_READ,
    PERM_NEWS_READ,
    PERM_SYSTEM_READ,
    PERM_DEV_DIAGNOSE,
}

# Permissions that always require explicit approval before use.
_REQUIRES_APPROVAL = {
    PERM_DEV_MODIFY,
}

# Tool name -> list of required permissions.
_TOOL_PERMISSIONS: Dict[str, List[str]] = {}

# Optional callback: approval_gate(action, description) -> bool.
# Set by the UI / operator. When None, approval-required actions are denied.
approval_gate: Optional[Callable[[str, str], bool]] = None


def bind_approval_gate(gate: Callable[[str, str], bool]) -> None:
    """Register the approval gate callback (wired from main.py's confirm gate)."""
    global approval_gate
    approval_gate = gate


def register_permissions(tool_name: str, permissions: List[str]) -> None:
    """Declare which permissions a tool requires."""
    with _lock:
        _TOOL_PERMISSIONS[tool_name] = list(permissions)


def required_permissions(tool_name: str) -> List[str]:
    """Return the permissions declared for a tool."""
    with _lock:
        return list(_TOOL_PERMISSIONS.get(tool_name, []))


def is_granted(permission: str) -> bool:
    """True if a permission is granted without needing the approval gate."""
    return permission in _SAFE_DEFAULTS


def needs_approval(permission: str) -> bool:
    """True if a permission requires explicit operator approval."""
    return permission in _REQUIRES_APPROVAL


def request_approval(action: str, description: str) -> bool:
    """
    Ask the approval gate whether `action` is allowed.

    Returns False when no gate is wired — safe by default: we never silently
    auto-approve a modification.
    """
    if approval_gate is None:
        return False
    try:
        return bool(approval_gate(action, description))
    except Exception:
        return False


_lock = __import__("threading").Lock()


def check_permissions(tool_name: str) -> List[str]:
    """
    Return the list of permissions for `tool_name` that are NOT yet granted.

    Empty list means the tool may run. Non-empty means the caller must obtain
    approval (via request_approval) for each missing approval-required
    permission before executing.
    """
    perms = required_permissions(tool_name)
    blocked: List[str] = []
    for p in perms:
        if p in _SAFE_DEFAULTS:
            continue
        blocked.append(p)
    return blocked


def grant_permission(permission: str) -> None:
    """Add a permission to the safe defaults (operator has approved it)."""
    with _lock:
        _SAFE_DEFAULTS.add(permission)
        _REQUIRES_APPROVAL.discard(permission)


def require_permission(permission: str) -> None:
    """Mark a permission as requiring explicit approval."""
    with _lock:
        _REQUIRES_APPROVAL.add(permission)
        _SAFE_DEFAULTS.discard(permission)
