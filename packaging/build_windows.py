"""
Build the MARK LV desktop app on Windows.

    python packaging/build_windows.py

Runs PyInstaller against the repository-root mark_liv.spec and leaves the app in
dist/MARK LV/. Re-running is safe: --clean wipes the intermediate build/ tree so
a stale cache from an older spec can never be what you ship.
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "MARK LV"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the MARK LV desktop app.")
    parser.add_argument(
        "--distpath",
        type=Path,
        default=ROOT / "dist",
        help="PyInstaller output directory (default: repository dist directory)",
    )
    parser.add_argument(
        "--workpath",
        type=Path,
        default=ROOT / "build",
        help="PyInstaller temporary work directory (default: repository build directory)",
    )
    args = parser.parse_args(argv)
    target = args.distpath.resolve() / APP_NAME
    user_state = [target / "config", target / "memory"]
    populated_state = [path for path in user_state if path.exists()]
    if populated_state:
        print(
            f"Refusing to replace {target}: it contains user state "
            f"({', '.join(str(path) for path in populated_state)}).\n"
            "Choose a fresh output directory with --distpath so API keys and "
            "memory are not deleted."
        )
        return 2

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "PyInstaller is not installed. Install the build tools first:\n"
            f"    {sys.executable} -m pip install -r "
            f"{Path(__file__).parent / 'requirements-build.txt'}"
        )
        return 1

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(ROOT / "mark_liv.spec"),
        "--noconfirm",
        "--clean",
        "--distpath", str(args.distpath.resolve()),
        "--workpath", str(args.workpath.resolve()),
    ]
    print("Building: " + " ".join(cmd))
    subprocess.run(cmd, check=True)

    exe = args.distpath.resolve() / APP_NAME / (
        f"{APP_NAME}.exe" if sys.platform == "win32" else APP_NAME
    )
    print(f"\nBuild complete: {exe}")
    print(
        "Smoke-check before shipping: launch the app, save your API key, quit,\n"
        f"and confirm config/api_keys.json now exists NEXT TO the exe — at\n"
        f"    {exe.parent / 'config' / 'api_keys.json'}\n"
        "If it is missing there (or appears under _internal/), frozen path\n"
        "resolution regressed — see tests/test_paths.py."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
