"""Regression tests for the application config manager."""

import ast
import json
from pathlib import Path

import pytest

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


def test_corrupted_json_is_recreated(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")

    cfg = Config("dev")

    assert cfg.data.MODE == "dev"
    recreated = json.loads(
        (tmp_path / "config.json").read_text(encoding="utf-8")
    )
    assert recreated["MODE"] == "dev"


def test_invalid_fields_are_recreated(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"PORT": "not-an-int"}), encoding="utf-8"
    )

    cfg = Config("dev")

    assert cfg.data.PORT == 9864


def test_load_errors_are_raised(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    cfg = Config("dev")

    def broken_load(path) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr(cfg, "load", broken_load)

    with pytest.raises(RuntimeError, match="boom"):
        cfg._load_or_create()


def test_save_failure_returns_false(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = Config("dev")

    target = tmp_path / "missing" / "config.json"
    assert cfg.save(target, cfg.data) is False