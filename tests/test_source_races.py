"""Sibling source paths for the account-generation regressions found in the Nextcloud review."""
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

import pytest

from castlib import config
from castlib.auth import browser, devicecode, loopback
from castlib.errors import AuthError
from castlib.sources import gopro, onedrive
from castlib.sources.gphotos import GPhotosSource
from castlib.sources.gopro import GoProSource
from castlib.sources.onedrive import OneDriveSource


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_CONFIG", str(tmp_path / "config"))
    monkeypatch.setattr(config, "_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("GOPRO_TOKEN", "synthetic")
    monkeypatch.setattr(browser, "remove_profile", lambda: None)


@pytest.mark.parametrize("provider", ["onedrive", "gphotos"])
@pytest.mark.parametrize("action", ["cancel", "disconnect"])
def test_sibling_pending_start_is_cancelled(monkeypatch, provider, action):
    entered, release = threading.Event(), threading.Event()
    cancelled = []
    if provider == "onedrive":
        src = OneDriveSource()
        flow = {"user_code": "test", "verification_uri": "https://test.invalid", "expires_in": 600, "message": "test"}
        monkeypatch.setattr(src, "_wait_for_token", lambda *args: None)
        target, name = devicecode, "start"
    else:
        src = GPhotosSource()
        flow = SimpleNamespace(auth_url="https://test.invalid", cancel=lambda: cancelled.append(True))
        monkeypatch.setattr(src, "_client_of", lambda: {})
        monkeypatch.setattr(src, "_wait_for_consent", lambda *args: None)
        target, name = loopback, "start"

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return flow

    monkeypatch.setattr(target, name, delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(src.connect, {})
        try:
            assert entered.wait(5)
            src.connect({"cancel": True}) if action == "cancel" else src.disconnect()
        finally:
            release.set()
        with pytest.raises(AuthError) as err:
            future.result(timeout=5)
    assert err.value.code == "cancelled"
    assert src.status()["state"] == "disconnected" and not src._store.exists()
    if provider == "gphotos":
        assert cancelled == [True]


@pytest.mark.parametrize("provider", ["onedrive", "gopro"])
@pytest.mark.parametrize("operation", ["list", "lookup"])
def test_sibling_late_result_cannot_refill_a_cleared_cache(monkeypatch, provider, operation):
    if provider == "onedrive":
        src = OneDriveSource()
        src._store.save({"access_token": "synthetic", "refresh_token": "synthetic", "expires_in": 3600})
        item = {"id": "51", "name": "old.jpg", "file": {"mimeType": "image/jpeg"}}

        def answer(*args):
            src.disconnect()
            return {"value": [item]} if operation == "list" else item

        monkeypatch.setattr(onedrive, "graph_get", answer)
    else:
        src = GoProSource()
        item = {"id": "51", "type": "Photo", "content_title": "old.jpg"}

        def answer(*args):
            src.disconnect()
            return [item] if operation == "list" else item

        monkeypatch.setattr(gopro, "search" if operation == "list" else "api", answer)
    with pytest.raises(AuthError) as err:
        src.list() if operation == "list" else src.resolve("51")
    assert err.value.code == "cancelled"
    assert not src._raw


def test_onedrive_late_verification_keeps_the_new_account(monkeypatch):
    src = OneDriveSource()
    src._store.save({"access_token": "synthetic-old", "refresh_token": "synthetic", "expires_in": 3600})

    def switched(*args):
        src.disconnect()
        with src._lock:
            src._store.save({"access_token": "synthetic-new", "refresh_token": "synthetic", "expires_in": 3600},
                            account={"displayName": "New"})
            src._gen += 1
            src._verified_at = 1
        return {"displayName": "Old"}

    monkeypatch.setattr(src, "_me", switched)
    src.connect({})
    assert src._store.account() == {"displayName": "New"}
