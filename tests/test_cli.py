import socket

import pytest

from castlib import cli


@pytest.fixture
def captured_cast(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "cast", lambda source, **kw: calls.append((source, kw)) or 0)
    return calls


def test_cloud_commands_honour_cast_tv(monkeypatch, captured_cast):
    monkeypatch.setenv("CAST_TV", "192.0.2.42")
    monkeypatch.setattr(cli.gopro, "share_url", lambda url: "https://cdn/x.mp4")
    monkeypatch.setattr(cli.sharelink, "resolve", lambda link, op: "https://cdn/y.mp4")
    assert cli.main_gopro(["https://gopro.com/v/abc"]) == 0
    assert cli.main_photos(["https://photos.app.goo.gl/x"]) == 0
    assert [kw["tv"] for _, kw in captured_cast] == ["192.0.2.42", "192.0.2.42"]


def test_explicit_tv_overrides_cast_tv(monkeypatch, captured_cast):
    monkeypatch.setenv("CAST_TV", "192.0.2.42")
    monkeypatch.setattr(cli.gopro, "share_url", lambda url: "https://cdn/x.mp4")
    assert cli.main_gopro(["https://gopro.com/v/abc", "-t", "192.0.2.7"]) == 0
    assert captured_cast[0][1]["tv"] == "192.0.2.7"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_cast_releases_port_and_retires_items_on_soap_failure(monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\0" * 100)
    subs = tmp_path / "clip.srt"
    subs.write_text("1\n", encoding="utf-8")
    servers = []

    class Recording(cli.Server):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            servers.append(self)

    def refuse(*a, **kw):
        raise OSError("TV said no")

    monkeypatch.setattr(cli, "Server", Recording)
    monkeypatch.setattr(cli, "find_tv", lambda tv: ("127.0.0.1", "http://127.0.0.1:1/avt"))
    monkeypatch.setattr(cli, "local_ip", lambda ip: "127.0.0.1")
    monkeypatch.setattr(cli, "soap", refuse)
    monkeypatch.setattr(cli, "check_codecs", lambda path: None)
    port = _free_port()
    assert cli.cast(str(clip), subs=str(subs), tv="127.0.0.1", port=port) == 1
    (srv,) = servers
    items = srv.registry.items()
    assert len(items) == 2
    assert all(i.retired_at is not None for i in items)
    # the port is free again: a second cast in the same process can bind it
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.close()
