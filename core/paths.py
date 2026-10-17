"""
One answer to "where is this file?", for both a source checkout and a frozen
(PyInstaller) build.

There are two different questions and they have two different answers:

* `resource_path(...)` — a read-only file shipped WITH the app: prompt.txt, the
  avatar mesh, the tray icon, the built-in actions and plugins. In a frozen
  build these live inside the bundle (`sys._MEIPASS`, which for a one-file build
  is a temporary folder that disappears on exit); in a checkout they sit beside
  the source.
* `data_dir()` — where the app WRITES state: the API key, long-term memory, the
  phone-dashboard TLS certs, uploads. This has to survive restarts, so in a
  frozen build it is the folder next to the executable — never the temp bundle.

`sys.frozen` and `sys._MEIPASS` are set only while a PyInstaller app runs; both
are read defensively so this module imports and behaves in a plain interpreter.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle, False from source."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Where shipped, read-only resources live.

    PyInstaller sets `sys._MEIPASS` to the folder it unpacked the app into — a
    temp dir in one-file mode, the install folder in one-folder mode. Without a
    bundle this is the repository root (this file is `core/paths.py`).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Where writable state lives: beside the executable when frozen, else the
    repository root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """A shipped, read-only file. `resource_path("core", "prompt.txt")`."""
    return bundle_dir().joinpath(*parts)


def data_path(*parts: str) -> Path:
    """A writable file beside the exe (frozen) or the repo (source)."""
    return data_dir().joinpath(*parts)
