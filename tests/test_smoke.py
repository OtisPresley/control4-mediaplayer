import importlib
import json
from pathlib import Path

PACKAGE = "custom_components.control4_mediaplayer"

def test_imports():
    mod = importlib.import_module(PACKAGE)
    assert mod is not None

def test_manifest_present():
    manifest = Path("custom_components/control4_mediaplayer/manifest.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for key in ("domain", "name", "version", "requirements"):
        assert key in data

