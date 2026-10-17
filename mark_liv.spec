# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the MARK LV desktop app (Windows first).

Build with:   python packaging/build_windows.py
       or:    python -m PyInstaller mark_liv.spec --noconfirm

Why onedir and not onefile: the app pulls in PyQt6, opencv and numpy. A onefile
build re-extracts all of that to a temp folder on every launch, so it starts
slowly and — more importantly — its `sys._MEIPASS` is that throwaway folder.
core/paths.py keeps writable state OUT of the bundle precisely so a frozen build
does not lose it, but onedir makes the split obvious on disk and starts fast.
The trade-off is a folder of files instead of a single .exe; wrap the folder in
an installer if a single download matters.

The assets listed in `datas` are what `core/paths.py::resource_path` expects to
find under `_internal/`. If you add a shipped, read-only file, add it here too.
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve()          # SPECPATH is set by PyInstaller
WINDOWS = os.name == "nt"


def _submodules(package):
    try:
        return collect_submodules(package)
    except Exception:
        return []


def _datafiles(package):
    try:
        return collect_data_files(package)
    except Exception:
        return []


# ── Shipped, read-only resources (end up in _internal/) ───────────────────────
datas = [
    (str(ROOT / "core" / "prompt.txt"), "core"),
    (str(ROOT / "core" / "face_model.obj"), "core"),
    (str(ROOT / "config" / "jarvis.ico"), "config"),
    (str(ROOT / "actions"), "actions"),
    (str(ROOT / "plugins"), "plugins"),
    (str(ROOT / "dashboard" / "static"), "dashboard/static"),
    (str(ROOT / "LICENSE"), "."),
]
# PortAudio ships as data inside sounddevice's _sounddevice_data package.
datas += _datafiles("_sounddevice_data")

# ── Imports PyInstaller cannot see by walking the AST ─────────────────────────
hiddenimports = [
    # uvicorn resolves protocol/loop/lifespan implementations by string name.
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    # websockets 12+ picks its speedups at runtime.
    "websockets.legacy",
    "websockets.legacy.client",
    "websockets.legacy.server",
]
# google-genai loads its generated submodules lazily.
hiddenimports += _submodules("google.genai")

# ── Nothing here is used; excluding keeps the build from ballooning ───────────
excludes = [
    "tkinter",
    "matplotlib",
    "IPython",
    "pytest",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineQuick",
    "PyQt6.QtBluetooth",
    "PyQt6.QtNfc",
    "PyQt6.QtPdf",
    "PyQt6.QtQuick3D",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MARK LV",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX can trip antivirus; size is not the goal
    console=os.environ.get("MARK_LV_CONSOLE") == "1",
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "config" / "jarvis.ico") if WINDOWS else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MARK LV",
)
