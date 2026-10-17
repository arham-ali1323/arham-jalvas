"""
Built by packaging/build_smoke.py and run as a REAL PyInstaller executable.

It exists to prove, inside an actual frozen bundle, the one thing a source
checkout cannot prove: that core/paths.py reports a different `bundle_dir`
(shipped resources) from `data_dir` (writable state), and that a bundled
resource is reachable. If `data_dir` ever points inside `_MEIPASS`, a packaged
build would throw away the user's API key on exit — this catches exactly that.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import bundle_dir, data_dir, data_path, is_frozen, resource_path

prompt = resource_path("core", "prompt.txt")
report = {
    "frozen": is_frozen(),
    "exe": sys.executable,
    "meipass": getattr(sys, "_MEIPASS", None),
    "bundle_dir": str(bundle_dir()),
    "data_dir": str(data_dir()),
    "data_dir_is_bundle": str(data_dir()) == str(bundle_dir()),
    "prompt_resource": str(prompt),
    "prompt_resource_exists": prompt.exists(),
    "api_key_path": str(data_path("config", "api_keys.json")),
}
print("SMOKE_REPORT " + json.dumps(report))
