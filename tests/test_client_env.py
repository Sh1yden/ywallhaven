"""Tests for the Flet client environment sanitizer."""

import os
import sys

import pytest

from app.interface.client_env import (
    patch_flet_client_env,
    scrub_bundle_lib_paths,
)


def test_scrub_removes_bundle_entries():
    env = {
        "LD_LIBRARY_PATH": "/opt/x:/b/_internal:/tmp/_MEIabc:/usr/lib",
        "OTHER": "1",
    }

    cleaned = scrub_bundle_lib_paths(env)

    assert cleaned["LD_LIBRARY_PATH"] == "/opt/x:/usr/lib"
    assert cleaned["OTHER"] == "1"
    assert env["LD_LIBRARY_PATH"].startswith("/opt/x:/b/")


def test_scrub_drops_var_when_only_bundle():
    cleaned = scrub_bundle_lib_paths({"LD_LIBRARY_PATH": "/b/_internal"})

    assert "LD_LIBRARY_PATH" not in cleaned


def test_scrub_keeps_clean_env():
    env = {"LD_LIBRARY_PATH": "/usr/lib", "A": "b"}

    assert scrub_bundle_lib_paths(env) == env


def test_patch_skipped_when_not_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    assert patch_flet_client_env() is False


@pytest.mark.native
@pytest.mark.native_linux
@pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only native test"
)
def test_patch_scrubs_real_seam(monkeypatch):
    import flet_desktop

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv(
        "LD_LIBRARY_PATH", "/b/_internal:/usr/lib", prepend=False
    )

    assert patch_flet_client_env() is True
    assert patch_flet_client_env() is False  # idempotent

    _cmd, env, _pid = flet_desktop.__locate_and_unpack_flet_view(
        "tcp://localhost:9", None, False
    )

    assert "_internal" not in env.get("LD_LIBRARY_PATH", "")
    assert "/usr/lib" in env.get("LD_LIBRARY_PATH", "")
    assert os.environ["LD_LIBRARY_PATH"].startswith("/b/")


def test_patch_missing_seam_returns_false(monkeypatch):
    import flet_desktop

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(
        flet_desktop, "__locate_and_unpack_flet_view", raising=False
    )

    assert patch_flet_client_env() is False
