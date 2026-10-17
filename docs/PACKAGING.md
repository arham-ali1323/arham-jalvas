# Packaging the desktop app

How to turn the MARK LV source tree into a Windows application, and why the
frozen build lays files out the way it does.

---

## What you get

`python packaging/build_windows.py` produces an **onedir** build:

```
dist/MARK LV/
├── MARK LV.exe                 # the bootloader + your Python
├── config/                     # created on first run — YOUR state lives here
│   └── api_keys.json
├── memory/
│   └── long_term.json
└── _internal/                  # everything shipped read-only
    ├── core/prompt.txt
    ├── core/face_model.obj
    ├── config/jarvis.ico
    ├── actions/*.py
    ├── plugins/*.py
    ├── dashboard/static/
    ├── PyQt6/  numpy/  cv2/  ...
    └── base_library.zip
```

The verified Windows output in this checkout is about **310 MB** (309.5 MB on
Python 3.13 / Windows 11); size varies with dependency versions. It contains
PyQt6, OpenCV, numpy and the Qt runtime. `onedir` was chosen over
`onefile` on purpose: a one-file build re-extracts all of that to a temp folder
on every launch, so it starts slowly **and** its bundle directory is throwaway —
which is the exact trap described below.

---

## Prerequisites

- Python **3.11–3.13** on the build machine (same floor as `setup.py`).
- Runtime dependencies and the build tool:

```powershell
python setup.py                                    # app deps + Playwright browsers
python -m pip install -r packaging/requirements-build.txt   # PyInstaller
```

---

## Build

```powershell
python packaging/build_windows.py
```

The script runs PyInstaller against [mark_liv.spec](../mark_liv.spec) in the repo
root, with `--clean` so a stale cache from an older spec can never be what you
ship. Output locations can be selected explicitly, which is useful when the
default `dist/MARK LV` already contains user configuration. The script refuses
to overwrite an existing package with `config/` or `memory/` state:

```powershell
python packaging/build_windows.py --distpath dist\preflight --workpath build\preflight-work
```

This produces a portable onedir folder, not an MSI or setup wizard. To build by
hand instead:

```
python -m PyInstaller mark_liv.spec --noconfirm --clean
```

Distribute only a clean package output. Do not upload the repository's whole
`dist/` tree or a previously launched user folder: `config/` and `memory/`
beside the executable hold local credentials and personal data.

Set `MARK_LV_CONSOLE=1` in the environment to build a **console** build, which is
what you want when a frozen launch is failing and you need to see a traceback.

---

## The one rule: state is never written inside the bundle

Every path in the app goes through `core/paths.py`, which answers two different
questions with two different answers:

| Question | Helper | Source checkout | Frozen build |
| --- | --- | --- | --- |
| A shipped, read-only file (prompt, mesh, icon, actions, plugins) | `resource_path(...)` | repo root | `sys._MEIPASS` (`_internal/`) |
| Where the app **writes** (API key, memory, TLS certs, uploads) | `data_dir()` | repo root | folder **beside the exe** |

`_MEIPASS` for a one-file build is a temp directory wiped on exit. If writable
state resolved there, the user's API key would silently vanish every time the
app closed — and it would look fine in a source checkout, which is why this is
pinned by a test.

### Verifying it

Two levels, both runnable without the GUI:

```powershell
python -m pytest tests/test_paths.py        # logic, in a normal interpreter
python packaging/build_smoke.py             # builds a real exe and checks it
```

`build_smoke.py` compiles a tiny program against `core/paths.py`, runs it, and
asserts that `data_dir` sits **outside** the bundle while `resource_path` still
reaches a shipped file. Run it after touching `core/paths.py` or the spec.

> If you add a new shipped, read-only file, add it to `datas` in `mark_liv.spec`
> **and** read it through `resource_path`, or it will not be in the build.

---

## Manual acceptance checklist

The build and boot are automated; these need a human once per release:

1. Launch `dist/MARK LV/MARK LV.exe`. The HUD appears and the setup screen asks
   for a Gemini key.
2. Paste a key and save. Quit the app.
3. Confirm `dist/MARK LV/config/api_keys.json` exists **beside the exe** — not
   under `_internal/`. This is the whole point of the path split.
4. Relaunch: it comes up already configured (state survived).
5. Exercise one voice command with a file-backed action and one plugin, and the
   phone dashboard (`dashboard/static/` shipped correctly).

---

## Things that need a hand outside the bundle

### Playwright browsers

`playwright`'s browsers (Chromium, Firefox) are **not** part of the build — they
are hundreds of megabytes downloaded per user. On the target machine, install
them once:

```
MARK LV.exe is a GUI; from the app's folder run:
  <python> -m playwright install chromium firefox
```

If you want them inside the bundle, point `PLAYWRIGHT_BROWSERS_PATH=0` at build
time so they are collected under `_internal/`, and document the extra size. This
project deliberately leaves them out and lets `setup.py` (or the user) fetch them.

### Local wake word

The "Hey Jarvis" model is opt-in and downloads on demand from the app
(⚙ → WAKE WORD); it is not bundled. It is stored under the user's data area, so
it survives rebuilds.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Exe exits instantly, no window | Rebuild with `$env:MARK_LV_CONSOLE="1"` to see the traceback; usually a hidden import. |
| `config/api_keys.json` missing after quit | Frozen path regression — run `packaging/build_smoke.py`; check nothing writes via `__file__` directly. |
| Avatar is a plain glowing core | `core/face_model.obj` was not bundled — check `_internal/core/face_model.obj`.
| Antivirus flags / slow start | `upx=False` is already set; add an exclusion for `dist/MARK LV/`.
| Warnings about `numpy._core.*` | Harmless PyInstaller noise (conditional re-exports), ignore.

---

## macOS / Linux

The spec and `core/paths.py` are cross-platform, but this has only been built and
tested on Windows. On macOS you would also produce a `.app` wrapper (and code
sign it); on Linux the onedir folder is already runnable. `build_windows.py` uses
`MARK LV.exe` on Windows and a plain `MARK LV` elsewhere.
