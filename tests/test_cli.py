import io
import os
import signal
import socket
import subprocess
import sys
import time

import pytest

from castlib import cli, dlna
from tests.conftest import FakeTV, finish_or_dump


@pytest.fixture
def captured_cast(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "cast", lambda source, **kw: calls.append((source, kw)) or 0)
    return calls


def test_cloud_commands_honour_cast_tv(monkeypatch, captured_cast):
    monkeypatch.setenv("CAST_TV", "192.0.2.42")
    monkeypatch.setattr(cli.gopro, "share_url", lambda url: "https://cdn/x.mp4")
    monkeypatch.setattr(cli.sharelink, "resolve", lambda link, cookies_path=None: "https://cdn/y.mp4")
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


@pytest.mark.skipif(sys.platform == "win32", reason="Windows cannot deliver SIGINT/SIGTERM to a child's handler")
def test_ui_prints_addresses_and_exits_cleanly_on_sigint(tmp_path):
    port = _free_port()
    env = dict(os.environ, HOME=str(tmp_path), PYTHONUNBUFFERED="1", PYTHONFAULTHANDLER="1")   # a hang prints its threads
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
        lines.append(finish_or_dump(proc, 15))
    finally:
        if proc.poll() is None:
            proc.kill()
    out = "".join(lines)
    addresses = [l for l in out.splitlines() if "/ui/" in l and "http://" in l]
    assert "http://localhost:%d/ui/" % port in out
    assert len(addresses) >= 1
    assert "Stopped." in out
    assert proc.returncode == 0, out


@pytest.mark.skipif(sys.platform == "win32", reason="SIGABRT and faulthandler's dump are POSIX here")
def test_finish_or_dump_names_the_waiting_frame():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import threading; print('up', flush=True); threading.Event().wait()"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env=dict(os.environ, PYTHONFAULTHANDLER="1"))
    assert proc.stdout.readline().strip() == "up"
    with pytest.raises(pytest.fail.Exception) as failed:
        finish_or_dump(proc, 1)
    text = str(failed.value)
    assert ("Current thread" in text or "Thread 0x" in text) and "in wait" in text, text


def test_ctrl_c_while_the_handler_is_installed_still_stops(app, monkeypatch, capsys):
    """CI caught SIGINT landing inside ``signal.signal``: it must still take the Ctrl+C path."""
    from castlib import app as app_module

    def interrupted(*a):
        raise KeyboardInterrupt
    monkeypatch.setattr(app_module.signal, "signal", interrupted)
    assert app.run_forever() == 0
    assert "Stopped." in capsys.readouterr().out
    assert "Stop" in app.tv_fake.actions()
    assert app._closed.is_set()


def test_ctrl_c_before_run_forever_takes_over(monkeypatch):
    from castlib import cli
    done = []

    class Early:
        def run_forever(self):
            raise KeyboardInterrupt              # arrived before run_forever's own try

        def shutdown(self):
            done.append("shutdown")
    monkeypatch.setattr(cli.App, "start", classmethod(lambda cls, *a, **k: Early()))
    assert cli.ui(port=1, browser=False) == 0
    assert done == ["shutdown"]


def _interrupted(*a, **kw):
    raise KeyboardInterrupt


def test_main_wait_behaves_like_event_wait():
    import threading
    from castlib.app import main_wait
    ev = threading.Event()
    start = time.monotonic()
    assert main_wait(ev, 0.1) is False
    assert time.monotonic() - start >= 0.1
    threading.Timer(0.05, ev.set).start()
    start = time.monotonic()
    assert main_wait(ev, 5.0) is True
    assert time.monotonic() - start < 1.0
    assert main_wait(ev, 0) is True                      # already set: True at once, like Event.wait


def test_ctrl_c_inside_main_wait_leaves_the_event_usable():
    """CI hung after "Stopped.": a Ctrl+C inside ``Event.wait`` can leave the Event's lock held."""
    import threading
    from castlib.app import main_wait
    ev = threading.Event()
    with pytest.raises(KeyboardInterrupt):
        main_wait(ev, 1.0, sleep=_interrupted)
    assert ev._cond._lock.acquire(timeout=1)
    ev._cond._lock.release()
    ev.set()                                             # what close() does next
    assert ev.is_set()


def test_run_forever_ctrl_c_in_its_wait_stops_and_closes(app, monkeypatch, capsys):
    from castlib import app as app_module
    monkeypatch.setattr(app_module.signal, "signal", lambda *a: None)   # pytest keeps its own SIGTERM
    monkeypatch.setattr(app_module, "main_wait", _interrupted)
    assert app.run_forever() == 0
    assert "Stopped." in capsys.readouterr().out
    assert "Stop" in app.tv_fake.actions()
    assert app._closed.is_set()


def test_run_forever_does_not_wait_on_the_event_in_the_main_thread(app, monkeypatch):
    import threading
    from castlib import app as app_module
    monkeypatch.setattr(app_module.signal, "signal", lambda *a: None)

    def forbidden(timeout=None):
        raise AssertionError("Event.wait in the main thread, where Ctrl+C lands")
    monkeypatch.setattr(app._closed, "wait", forbidden)
    threading.Timer(0.2, app._closed.set).start()        # what another thread's close() does
    assert app.run_forever() == 0


def test_cast_and_show_ctrl_c_in_their_wait_print_stopped(cli_env, tmp_path, monkeypatch, capsys):
    servers, tv = cli_env
    tv.video_script = ["PLAYING"]
    monkeypatch.setattr(cli, "main_wait", _interrupted)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\0" * 100)
    assert cli.cast(str(clip), tv="127.0.0.1", port=_free_port()) == 0
    assert "Stopped." in capsys.readouterr().out
    assert cli.show([str(clip), str(clip)], tv="127.0.0.1", port=_free_port()) == 0
    assert "Stopped." in capsys.readouterr().out


@pytest.fixture
def start_env(monkeypatch, tmp_path):
    """``App.start`` in this process: tmp config and cache, no discovery; pytest's SIGTERM handler is restored."""
    from castlib import app as app_module, config
    monkeypatch.setattr(config, "_CONFIG", str(tmp_path / "config"))
    monkeypatch.setattr(config, "_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(config, "VIDEO_BASE", str(tmp_path))
    monkeypatch.setattr(app_module, "discover", lambda **kw: [])
    before = signal.getsignal(signal.SIGTERM)
    try:
        yield app_module
    finally:
        signal.signal(signal.SIGTERM, before)


def _port_is_free(port):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def test_start_installs_the_sigterm_handler_before_its_first_line(start_env):
    """CI's SIGTERM test reads a line and sends a kill: the handler must already be there."""
    seen = []

    class Recorder:
        def write(self, text):
            if not seen:
                seen.append(signal.getsignal(signal.SIGTERM))

        def flush(self):
            pass
    app = start_env.App.start(_free_port(), browser=False, out=Recorder())
    try:
        (handler,) = seen[:1]
        assert callable(handler)
        with pytest.raises(KeyboardInterrupt):
            handler(signal.SIGTERM, None)
    finally:
        app.close()


def test_start_leaves_out_stale_addresses(start_env, monkeypatch):
    """Wi-Fi off on Windows: its Deprecated address is neither the phone address nor another one."""
    monkeypatch.setattr(start_env, "stale_addresses", lambda: {"192.168.50.242"})
    monkeypatch.setattr(start_env, "local_ip", lambda target: "192.168.50.242")
    asked = []
    monkeypatch.setattr(start_env, "lan_interfaces",
                        lambda stale: asked.append(stale) or [("Hyper-V", "172.27.112.1")])
    port = _free_port()
    app = start_env.App.start(port, browser=False, out=io.StringIO())
    try:
        assert app.addresses == ["http://localhost:%d/ui/" % port, "http://172.27.112.1:%d/ui/" % port]
        assert asked == [{"192.168.50.242"}]
    finally:
        app.close()


def test_ctrl_c_during_start_stops_and_frees_the_port(start_env, monkeypatch, capsys):
    port = _free_port()
    monkeypatch.setattr(start_env, "firewall_blocked", _interrupted)   # called after the addresses are printed
    assert cli.ui(port=port, browser=False) == 0
    out = capsys.readouterr().out
    assert "http://localhost:%d/ui/" % port in out and "Stopped." in out
    assert _port_is_free(port)


def test_ctrl_c_before_the_app_exists_frees_the_port(start_env, monkeypatch, capsys):
    port = _free_port()
    monkeypatch.setattr(start_env.App, "__init__", _interrupted)
    assert cli.ui(port=port, browser=False) == 0
    assert "Stopped." not in capsys.readouterr().out       # nothing had started, so nothing to stop
    assert _port_is_free(port)


def test_ctrl_c_before_the_http_loop_runs_does_not_hang(start_env, monkeypatch):
    """``server.shutdown()`` waits for a ``serve_forever`` loop; before ``serve()`` none ever ran."""
    import threading
    port = _free_port()
    monkeypatch.setattr(start_env.App, "serve", _interrupted)
    result = []
    t = threading.Thread(target=lambda: result.append(cli.ui(port=port, browser=False)), daemon=True)
    t.start()
    t.join(5)
    assert result == [0], "cli.ui did not return: close() waited for an HTTP loop that never started"
    assert _port_is_free(port)


def test_cast_and_show_ctrl_c_before_the_http_loop_runs_do_not_hang(cli_env, tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(cli.App, "serve", _interrupted)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\0" * 100)
    for run in (lambda: cli.cast(str(clip), tv="127.0.0.1", port=_free_port()),
                lambda: cli.show([str(clip), str(clip)], tv="127.0.0.1", port=_free_port())):
        raised = []

        def target():
            try:
                run()
            except KeyboardInterrupt:
                raised.append(True)
        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(5)
        assert raised == [True], "the CLI did not return: close() waited for an HTTP loop that never started"


def test_failed_bind_leaves_sigterm_alone(app, start_env, upstream):
    from castlib.app import AlreadyRunning
    before = signal.getsignal(signal.SIGTERM)
    with pytest.raises(AlreadyRunning):
        start_env.App.start(app.server.port, browser=False)
    other = upstream(b"<html>", ctype="text/html")
    with pytest.raises(OSError):
        start_env.App.start(other.server_address[1], browser=False)
    assert signal.getsignal(signal.SIGTERM) is before


def test_startup_failure_is_reported_before_any_window(app, start_env, upstream, monkeypatch, capsys):
    """A port held by another program: the text and exit 1 as before, the report (a message box when
    double-clicked on Windows) with the same text, and no window or tab is started."""
    from castlib import platform, window
    reported, windows = [], []
    monkeypatch.setattr(platform, "report_startup_error", reported.append)
    monkeypatch.setattr(window, "installed", lambda: True)
    monkeypatch.setattr(cli, "_in_window", lambda app: windows.append(app) or "closed")
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: windows.append(url))
    other = upstream(b"<html>", ctype="text/html")
    port = other.server_address[1]
    assert cli.ui(port=port) == 1
    out = capsys.readouterr().out
    (message,) = reported
    assert message.startswith("Cannot bind port %d: " % port) and message in out
    assert windows == []

    def broken(cls, port, **kw):
        raise RuntimeError("the config directory is not writable")
    monkeypatch.setattr(cli.App, "start", classmethod(broken))
    reported.clear()
    assert cli.ui(port=port) == 1
    assert reported == ["cast-tv could not start: the config directory is not writable"]
    assert "RuntimeError" in capsys.readouterr().err   # the traceback stays for a bug report


def test_ctrl_c_and_second_launch_are_not_startup_errors(app, start_env, monkeypatch):
    """Ctrl+C while starting and handing over to the cast-tv already running are no failures: no report."""
    from castlib import platform
    reported = []
    monkeypatch.setattr(platform, "report_startup_error", reported.append)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: None)
    assert cli.ui(port=app.server.port) == 0                          # AlreadyRunning
    monkeypatch.setattr(cli.App, "start", classmethod(lambda cls, port, **kw: (_ for _ in ()).throw(KeyboardInterrupt())))
    assert cli.ui(port=1) == 0
    assert reported == []


def test_no_window_extra_keeps_tab(start_env, monkeypatch, capsys):
    """pipx without ``[window]``: the tab and the console, as before S-12."""
    from castlib import window
    monkeypatch.setitem(sys.modules, "webview", None)
    assert not window.installed()
    opened, served = [], []
    monkeypatch.setattr(start_env.webbrowser, "open", opened.append)
    monkeypatch.setattr(start_env.App, "run_forever", lambda self: served.append(self) or 0)
    port = _free_port()
    assert cli.ui(port=port) == 0
    (app,) = served
    app.close()
    assert opened == ["http://localhost:%d/ui/" % port]
    assert "Ctrl+C ends it (playback stops on the TV too)" in capsys.readouterr().out


def test_second_launch_asks_for_the_window(app, start_env, monkeypatch, capsys):
    """The running cast-tv brings its window forward and the new launch exits; with no window, a tab."""
    from castlib import window
    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    port = app.server.port
    assert cli.ui(port=port) == 0                          # the running one has no window: POST answers false
    assert opened == ["http://127.0.0.1:%d/ui/" % port]
    monkeypatch.setattr(window, "show", lambda: True)
    opened.clear()
    assert cli.ui(port=port) == 0
    assert opened == []
    assert "Its window is in front." in capsys.readouterr().out
    assert cli.ui(port=port, windowed=False) == 0          # --no-window: the tab, without asking
    assert opened == ["http://127.0.0.1:%d/ui/" % port]
    opened.clear()
    assert cli.ui(port=port, browser=False) == 0           # --no-browser: neither
    assert opened == []


@pytest.fixture
def consent_env(start_env, monkeypatch, tmp_path):
    """A Google client file and recorders for the UI tab and for the consent browser."""
    import json
    from castlib.auth import loopback
    client = tmp_path / "client.json"
    client.write_text(json.dumps({"installed": {"client_id": "client-test", "client_secret": "secret-test",
                                                "redirect_uris": ["http://localhost"]}}), encoding="utf-8")
    monkeypatch.setenv("GOOGLE_CLIENT_JSON", str(client))
    tabs, consents = [], []
    monkeypatch.setattr(start_env.webbrowser, "open", tabs.append)
    monkeypatch.setattr(loopback, "open_browser", lambda url: consents.append(url) or True)
    return start_env, tabs, consents


def test_ui_tab_and_consent_browser_are_separate(consent_env):
    """The window turns the UI tab off but keeps Google's consent; --no-browser turns off both."""
    start_env, tabs, consents = consent_env
    cases = (({"browser": True, "open_ui": False}, False, True),      # window mode
             ({"browser": False, "open_ui": False}, False, False),    # --no-browser
             ({"browser": True}, True, True),                         # callers without open_ui: as before
             ({"browser": False}, False, False))
    for kw, tab, consent in cases:
        app = start_env.App.start(_free_port(), out=io.StringIO(), **kw)
        try:
            d = app.sources["gphotos"].connect({})
            assert d["step"] == "consent", kw
        finally:
            app.close()
        assert bool(tabs) is tab and bool(consents) is consent, kw
        tabs.clear()
        consents.clear()


def test_ui_passes_the_window_policy_to_start(monkeypatch):
    """Normal window mode keeps the consent browser; explicit --no-browser opens neither UI nor consent."""
    from castlib import window
    seen = []

    class Tab:
        def run_forever(self):
            return 0
    monkeypatch.setattr(cli.App, "start", classmethod(lambda cls, port, **kw: seen.append(kw) or Tab()))
    monkeypatch.setattr(cli, "_in_window", lambda app: "unavailable: test")
    monkeypatch.setattr(window, "installed", lambda: True)
    assert cli.ui(port=1) == 0
    assert cli.ui(port=1, browser=False) == 0
    assert [(kw["browser"], kw["open_ui"]) for kw in seen] == [(True, False), (False, False)]


def test_version_names_the_client(monkeypatch, tmp_path, capsys):
    """``--version``: the version, where the Google Photos client would come from, the GoPro window's browser."""
    import castlib
    from castlib import config, window
    from castlib.auth import _builtin_client
    monkeypatch.setattr(config, "_CONFIG", str(tmp_path / "config"))
    monkeypatch.delenv("GOOGLE_CLIENT_JSON", raising=False)
    monkeypatch.setattr(_builtin_client, "CLIENT_ID", None)
    monkeypatch.setattr(_builtin_client, "CLIENT_SECRET", None)
    exe = tmp_path / "chrome"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setenv("CAST_TV_BROWSER", str(exe))
    monkeypatch.setattr(window, "describe", lambda: "Window: edgechromium")
    assert cli.main_tv(["--version"]) == 0
    assert capsys.readouterr().out.splitlines() == ["cast-tv " + castlib.__version__, "Google Photos client: none",
                                                    "GoPro window: CAST_TV_BROWSER=" + str(exe),
                                                    "Window: edgechromium"]
    monkeypatch.setattr(_builtin_client, "CLIENT_ID", "id")
    monkeypatch.setattr(_builtin_client, "CLIENT_SECRET", "secret")
    cli.main_tv(["--version"])
    assert capsys.readouterr().out.splitlines()[1] == "Google Photos client: built in"
    monkeypatch.setenv("GOOGLE_CLIENT_JSON", str(tmp_path / "mine.json"))
    cli.main_tv(["--version"])
    assert capsys.readouterr().out.splitlines()[1] == "Google Photos client: from " + str(tmp_path / "mine.json")


def test_version_names_the_gopro_window(monkeypatch, tmp_path, capsys):
    """The third line comes from ``browser.describe()``; nothing is launched."""
    from castlib.auth import browser
    launched = []
    monkeypatch.setattr(browser, "launch", lambda *a, **kw: launched.append(a))
    monkeypatch.setenv("CAST_TV_BROWSER", "/nonexistent")
    assert cli.main_tv(["--version"]) == 0
    assert capsys.readouterr().out.splitlines()[2] == "GoPro window: CAST_TV_BROWSER=/nonexistent (not found)"
    monkeypatch.delenv("CAST_TV_BROWSER")
    monkeypatch.setattr(browser, "candidates", lambda **kw: ["/usr/bin/google-chrome", "/usr/bin/chromium"])
    cli.main_tv(["--version"])
    assert capsys.readouterr().out.splitlines()[2] == "GoPro window: /usr/bin/google-chrome"
    monkeypatch.setattr(browser, "candidates", lambda **kw: [])
    cli.main_tv(["--version"])
    assert capsys.readouterr().out.splitlines()[2] == "GoPro window: none found (token paste only)"
    assert launched == []


def test_gopro_without_a_token_points_at_the_ui(monkeypatch, tmp_path, capsys):
    """``cast-gopro`` with nothing stored names the UI route before the devtools steps; ``--token`` says the same."""
    from castlib import config
    monkeypatch.setattr(config, "_CONFIG", str(tmp_path / "config"))
    monkeypatch.delenv("GOPRO_TOKEN", raising=False)
    assert cli.main_gopro([]) == 1
    err = capsys.readouterr().err
    lines = err.splitlines()
    assert lines[0] == "No GoPro token stored."
    assert lines[1].startswith("Run cast-tv, open the GoPro tab and press Open gopro.com.")
    assert err.index("Run cast-tv") < err.index("F12") < err.index("checked 2026-09-20")
    assert "lasts a few hours" not in err and "GoPro sign-in" not in err
    monkeypatch.setenv("COLUMNS", "200")                       # argparse wraps help at the terminal width
    with pytest.raises(SystemExit):
        cli.main_gopro(["--help"])
    assert "the UI's Open gopro.com is the usual route" in capsys.readouterr().out


def test_self_check_converts_a_heic(capsys):
    """The release smoke test's probe: a HEIC made in memory comes out as a JPEG."""
    assert cli.main_tv(["--self-check"]) == 0
    assert capsys.readouterr().out.strip() == "self-check: HEIC -> image/jpeg 16x16 OK"


def test_window_check_flag_runs_the_probe_only(monkeypatch, capsys):
    """``--window-check`` returns the probe's exit code and starts nothing else; ``--help`` does not list it."""
    calls = []
    monkeypatch.setattr(cli, "window_check", lambda: calls.append("check") or 1)
    monkeypatch.setattr(cli, "ui", lambda **kw: calls.append("ui") or 0)
    assert cli.main_tv(["--window-check"]) == 1
    assert calls == ["check"]
    monkeypatch.setenv("COLUMNS", "200")
    with pytest.raises(SystemExit):
        cli.main_tv(["--help"])
    out = capsys.readouterr().out
    assert "--window-check" not in out and "--self-check" not in out
    assert "which engine the cast-tv window would use" in out
