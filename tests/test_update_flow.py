"""Regression tests for the update dialog client ownership.

The updater HTTP client must stay open when a release is handed over
to the dialog, and must be closed once the dialog is dismissed or the
update pipeline finishes.
"""

import asyncio
import json
from pathlib import Path

import pytest

import app.interface.components.update_dialog as dialog_module
from app.interface.components.update_dialog import UpdateDialog
from app.schemas import ReleaseInfo


class FakeUpdater:
    """Stand-in for UpdaterService tracking close() calls."""

    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.closed = False

    async def check_update(self) -> ReleaseInfo | None:
        if self.error is not None:
            raise self.error
        return self.result

    async def close(self) -> None:
        self.closed = True


def _release() -> ReleaseInfo:
    return ReleaseInfo(
        tag_name="v0.7.2",
        version="0.7.2",
        body="",
        assets=[{"name": "ywallhaven.exe", "url": "https://x/y.exe"}],
    )


class FakePage:
    """Minimal page stand-in recording show_dialog calls."""

    def __init__(self) -> None:
        self.shown: list[object] = []
        self.tasks: list = []

    def show_dialog(self, dialog: object) -> None:
        self.shown.append(dialog)

    def pop_dialog(self) -> None:
        pass

    def run_task(self, fn, *args) -> None:
        self.tasks.append(fn(*args))


@pytest.fixture
def fake_updater_factory(monkeypatch):
    instances: list[FakeUpdater] = []
    monkeypatch.setattr(dialog_module, "_startup_checked", False)

    def factory(*, result=None, error=None) -> FakeUpdater:
        instance = FakeUpdater(result=result, error=error)
        instances.append(instance)
        return instance

    async def install(*, result=None, error=None) -> FakeUpdater:
        instance = factory(result=result, error=error)
        monkeypatch.setattr(
            dialog_module,
            "UpdaterService",
            lambda: instance,
        )
        return instance

    install.instances = instances
    return install


@pytest.mark.asyncio
async def test_client_stays_open_when_release_offered(
    fake_updater_factory,
) -> None:
    updater = await fake_updater_factory(result=_release())
    page = FakePage()

    await dialog_module.check_and_offer(page, manual=False)

    assert not updater.closed, "client must stay open for the dialog"
    assert len(page.shown) == 1  # the offer dialog was shown


@pytest.mark.asyncio
async def test_client_closed_on_check_error(fake_updater_factory) -> None:
    updater = await fake_updater_factory(error=RuntimeError("boom"))
    page = FakePage()

    await dialog_module.check_and_offer(page, manual=False)

    assert updater.closed
    assert page.shown == []


@pytest.mark.asyncio
async def test_client_closed_when_no_new_release(fake_updater_factory) -> None:
    updater = await fake_updater_factory(result=None)
    page = FakePage()

    await dialog_module.check_and_offer(page, manual=False)

    assert updater.closed
    assert page.shown == []


@pytest.mark.asyncio
async def test_dialog_close_releases_client(fake_updater_factory) -> None:
    updater = await fake_updater_factory(result=_release())
    page = FakePage()
    dialog = UpdateDialog(page, updater, _release())

    dialog._close()

    await asyncio.gather(*page.tasks)
    assert updater.closed, "dialog dismissal must close the client"


def test_install_closes_client_before_destroy(fake_updater_factory) -> None:
    """The download pipeline must release the client before destroying
    the window."""

    async def main() -> None:
        updater = await fake_updater_factory(result=_release())
        page = FakePage()
        dialog = UpdateDialog(page, updater, _release())
        updater.closed = False

        destroyed: list[bool] = []

        class WindowStub:
            async def destroy(self) -> None:
                destroyed.append(updater.closed)

        class Shim(FakePage):
            window = WindowStub()

        dialog.page = Shim()
        dialog._status = type("Stub", (), {
            "value": "",
            "update": lambda self: None,
        })()

        async def fake_download(release, *, progress=None):
            return Path("/tmp/ywallhaven-update-test.exe")

        updater.download_asset = fake_download
        updater.find_asset = lambda release: release.assets[0]
        updater.verify_sha256 = lambda path, asset: True
        updater.launch_updater = lambda path: True
        await dialog._install()

        assert destroyed == [True], "client must be closed before destroy"

    asyncio.run(main())


def test_release_payload_json_roundtrip() -> None:
    """Sanity guard for the fixture payload used in dialog tests."""
    payload = json.loads(_release().model_dump_json())
    assert payload["tag_name"] == "v0.7.2"