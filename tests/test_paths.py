"""Frozen-build path resolution.

The whole point of core/paths.py is that these two answers DIFFER once frozen:
shipped resources come from the bundle, writable state sits beside the exe. A
mistake here looks fine in a source checkout and silently loses the user's API
key in a packaged build, so it is worth pinning down.
"""
import importlib
import sys
from pathlib import Path

import pytest

from core import paths as paths_mod
from core.paths import bundle_dir, data_dir, data_path, is_frozen, resource_path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _unfreeze(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)


def test_source_checkout_reads_and_writes_at_repo_root(monkeypatch):
    _unfreeze(monkeypatch)
    assert not is_frozen()
    assert data_dir() == REPO_ROOT
    assert bundle_dir() == REPO_ROOT
    assert resource_path("core", "prompt.txt") == REPO_ROOT / "core" / "prompt.txt"
    assert data_path("config", "api_keys.json") == REPO_ROOT / "config" / "api_keys.json"


def test_frozen_build_separates_bundle_from_data(monkeypatch, tmp_path):
    exe_dir = tmp_path / "MarkLV"
    exe_dir.mkdir()
    bundle = tmp_path / "_MEI12345"
    bundle.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "MarkLV.exe"))

    assert is_frozen()
    assert data_dir() == exe_dir
    assert bundle_dir() == bundle
    assert data_dir() != bundle_dir()
    assert resource_path("config", "jarvis.ico") == bundle / "config" / "jarvis.ico"
    assert data_path("config", "api_keys.json") == exe_dir / "config" / "api_keys.json"


def test_stateful_module_follows_data_dir_when_frozen(tmp_path):
    """End-to-end: the config module must not write into the temp bundle."""
    from memory import config_manager

    exe_dir = tmp_path / "MarkLV"
    exe_dir.mkdir()
    bundle = tmp_path / "_MEI99999"
    bundle.mkdir()

    sentinel = object()
    old_frozen = getattr(sys, "frozen", sentinel)
    old_meipass = getattr(sys, "_MEIPASS", sentinel)
    old_exe = sys.executable

    sys.frozen = True
    sys._MEIPASS = str(bundle)
    sys.executable = str(exe_dir / "MarkLV.exe")
    try:
        importlib.reload(config_manager)
        assert config_manager.get_base_dir() == exe_dir
        assert config_manager.CONFIG_FILE == exe_dir / "config" / "api_keys.json"
    finally:
        if old_frozen is sentinel:
            del sys.frozen
        else:
            sys.frozen = old_frozen
        if old_meipass is sentinel:
            del sys._MEIPASS
        else:
            sys._MEIPASS = old_meipass
        sys.executable = old_exe
        importlib.reload(config_manager)

    assert config_manager.CONFIG_FILE == REPO_ROOT / "config" / "api_keys.json"


@pytest.mark.parametrize(
    "rel",
    [("core", "prompt.txt"), ("core", "face_model.obj"), ("config", "jarvis.ico")],
)
def test_shipped_resources_exist(rel):
    assert REPO_ROOT.joinpath(*rel).exists()


def test_resource_path_reexports_helper(monkeypatch, tmp_path):
    bundle = tmp_path / "b"
    bundle.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    assert paths_mod.resource_path("core", "prompt.txt") == bundle / "core" / "prompt.txt"
