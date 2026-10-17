"""
Build the frozen-path smoke test and run it.

    python packaging/build_smoke.py

Proves, inside a real PyInstaller executable, the one thing a source checkout
cannot: that core/paths.py keeps `data_dir` (writable state) OUTSIDE the bundle
while `resource_path` still reaches shipped files. Run it after touching
packaging or core/paths.py, before trusting a full build.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "mkpathcheck"
SEP = ";" if sys.platform == "win32" else ":"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mark_lv_smoke_") as tmp:
        tmp_path = Path(tmp)
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onedir", "--noconfirm", "--clean",
            "--name", NAME,
            "--distpath", str(tmp_path / "dist"),
            "--workpath", str(tmp_path / "work"),
            "--specpath", str(tmp_path / "spec"),
            "--add-data", f"{ROOT / 'core' / 'prompt.txt'}{SEP}core",
            str(ROOT / "packaging" / "smoke_frozen_paths.py"),
        ]
        print("Building smoke binary: " + " ".join(cmd))
        subprocess.run(cmd, check=True)

        binary = tmp_path / "dist" / NAME / (f"{NAME}.exe" if sys.platform == "win32" else NAME)
        print("Running: " + str(binary))
        run = subprocess.run([str(binary)], check=True, capture_output=True, text=True)

        line = next((l for l in run.stdout.splitlines() if l.startswith("SMOKE_REPORT")), None)
        if not line:
            print("No SMOKE_REPORT in output:\n" + run.stdout + run.stderr)
            return 2

        report = json.loads(line[len("SMOKE_REPORT "):])
        print(json.dumps(report, indent=2))

        checks = {
            "frozen": report["frozen"] is True,
            "data_dir outside bundle": report["data_dir_is_bundle"] is False,
            "bundled resource reachable": report["prompt_resource_exists"] is True,
            "data path beside exe (not _internal)": "_internal" not in report["api_key_path"],
        }
        for name, passed in checks.items():
            print(f"  [{'ok' if passed else 'FAIL'}] {name}")
        ok = all(checks.values())
        print("\nSMOKE " + ("PASS" if ok else "FAIL"))
        return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
