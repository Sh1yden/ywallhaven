"""Tests for the version resolution fallbacks."""

import importlib
import importlib.metadata
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest


def test_version_metadata_fallback_is_zeroed(monkeypatch) -> None:
    import app.core.version as version_module

    built = Path(version_module.__file__).parent / "_version.py"
    if built.exists():
        pytest.skip("built _version.py present; fallback not exercised")

    def fake_version(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", fake_version)
    importlib.reload(version_module)

    assert version_module.__version__ == "0.0.0"


def test_version_is_a_nonempty_string() -> None:
    import app.core.version as version_module

    assert isinstance(version_module.__version__, str)
    assert version_module.__version__