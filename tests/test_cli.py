import os
import signal
import socket
import subprocess
import sys
import time

import pytest

from castlib import cli, dlna
from tests.conftest import FakeTV


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


@pytest.fixture
def cli_env(monkeypatch, tmp_path, fast_supervisor):
    """A CLI run with the TV found, SOAP faked, and the config dir in tmp; yields the recording list."""
    from castlib import config
    monkeypatch.setattr(config, "_CONFIG", str(tmp_path / "config"))
    servers = []

    class Recording(cli.Server):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            servers.append(self)
    monkeypatch.setattr(cli, "Server", Recording)
    monkeypatch.setattr(cli, "find_tv", lambda tv: ("127.0.0.1", "http://127.0.0.1:1/avt", "Fake"))
    monkeypatch.setattr(cli, "check_codecs", lambda path: ([], None))
    tv = FakeTV(lambda: servers[0].registry)
    monkeypatch.setattr(dlna, "soap", tv.soap)
    return servers, tv


def test_cast_releases_port_and_retires_items_on_soap_failure(cli_env, tmp_path):
    servers, tv = cli_env
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\0" * 100)
    subs = tmp_path / "clip.srt"
    subs.write_text("1\n", encoding="utf-8")
    tv.fail = True
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


def test_cast_refused_before_start_prints_the_hint(cli_env, tmp_path, capsys):
    from castlib.platform import firewall_hint
    servers, tv = cli_env
    tv.faults = {"SetAVTransportURI": "716"}
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\0" * 100)
    port = _free_port()
    assert cli.cast(str(clip), tv="127.0.0.1", port=port) == 1
    out = capsys.readouterr().out
    assert "never asked for the file" in out
    assert firewall_hint(port) in out


def test_cast_follows_playback_to_the_end(cli_env, tmp_path, capsys):
    servers, tv = cli_env
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\0" * 100)
    assert cli.cast(str(clip), tv="127.0.0.1", port=_free_port()) == 0
    (srv,) = servers
    (entry,) = srv.app.local.entries()                    # the UI can re-cast it, by an opaque id
    assert entry.name == "clip" and entry.id != str(clip) and "/" not in entry.id
    out = capsys.readouterr().out
    assert ">  clip" in out and "serving from http://127.0.0.1:" in out
    assert "Finished." in out
    assert tv.actions()[:2] == ["SetAVTransportURI", "Play"]


def test_cast_replaced_from_the_ui_keeps_serving(cli_env, tmp_path, capsys):
    import threading
    from castlib.sources.local import item_for_path
    from tests.conftest import wait_for
    servers, tv = cli_env
    tv.video_script = ["PLAYING"]
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\0" * 100)
    other = tmp_path / "other.mp4"
    other.write_bytes(b"\0" * 100)
    result = []
    t = threading.Thread(target=lambda: result.append(cli.cast(str(clip), tv="127.0.0.1", port=_free_port())))
    t.start()
    wait_for(lambda: servers and servers[0].app is not None and servers[0].app.current is not None
             and servers[0].app.current.sent.is_set())
    app = servers[0].app
    first = app.current
    second = app.cast(item_for_path(str(other)))          # what POST /api/cast does
    assert second.sent.wait(5)
    wait_for(lambda: first.state == "replaced")
    time.sleep(0.3)
    assert t.is_alive()                                    # the CLI did not exit and tear the server down
    assert app.registry.get(second.item.id) is second.item
    app._closed.set()                                      # what Ctrl+C would do
    t.join(5)
    assert result == [0]
    assert "Taken over from the UI" in capsys.readouterr().out


def test_cli_show_runs_items_in_order(cli_env, tmp_path, capsys):
    servers, tv = cli_env
    paths = []
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        p = tmp_path / name
        p.write_bytes(b"\0" * 50)
        paths.append(str(p))
    assert cli.main_tv(paths + ["-t", "127.0.0.1", "-p", str(_free_port()), "-i", "2"]) == 0
    (srv,) = servers
    titles = [srv.registry.get(i).title for i in tv.uri_ids()]
    assert titles == ["a", "b", "c"]
    out = capsys.readouterr().out
    assert "Slideshow: 3 items" in out and "Show finished." in out


def test_slideshow_refuses_addresses_and_subs(cli_env, tmp_path, capsys):
    p = tmp_path / "a.jpg"
    p.write_bytes(b"x")
    assert cli.show([str(p), "https://example.com/x.mp4"]) == 1
    assert "takes local files" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main_tv([str(p), str(p), "-s", "x.srt"])


def test_ui_prints_addresses_and_exits_cleanly_on_sigint(tmp_path):
    port = _free_port()
    env = dict(os.environ, HOME=str(tmp_path), PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(
        [sys.executable, "-m", "castlib", "-p", str(port), "--no-browser", "-t", "127.0.0.1"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    lines = []
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            lines.append(line)
            if "does not expose AVTransport" in line or "TV:" in line:
                break
        proc.send_signal(signal.SIGINT)
        rest, _ = proc.communicate(timeout=15)
        lines.append(rest)
    finally:
        if proc.poll() is None:
            proc.kill()
    out = "".join(lines)
    addresses = [l for l in out.splitlines() if "/ui/" in l and "http://" in l]
    assert "http://localhost:%d/ui/" % port in out
    assert len(addresses) >= 1
    assert "Stopped." in out
    assert proc.returncode == 0, out
