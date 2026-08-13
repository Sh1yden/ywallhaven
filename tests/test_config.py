"""Regression tests for the application config manager."""

import ast
import json
from pathlib import Path

from app.core.config import Config


def _config_src() -> str:
    """Read the config manager source for structural checks."""
    root = Path(__file__).resolve().parent.parent
    return (root / "app" / "core" / "config.py").read_text(encoding="utf-8")


def test_update_is_a_method_of_config_class() -> None:
    """The update handler must live inside Config, not at module level."""
    tree = ast.parse(_config_src())
    config_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Config"
    )
    method_names = [
        node.name
        for node in config_class.body
        if isinstance(node, ast.FunctionDef)
    ]
    assert "update" in method_names


def test_update_merges_and_persists(tmp_path, monkeypatch) -> None:
    """Config.update must change the data and write the file back."""
    monkeypatch.chdir(tmp_path)
    cfg = Config("dev")

    assert cfg.data.THEME == "dark"

    ok = cfg.update(THEME="light", APIK="test-key")
    assert ok is True
    assert cfg.data.THEME == "light"

    persisted = json.loads(
        (tmp_path / "config.json").read_text(encoding="utf-8")
    )
    assert persisted["THEME"] == "light"
    assert persisted["APIK"] == "test-key"