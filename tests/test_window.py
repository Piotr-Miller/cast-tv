"""The cast-tv window (S-12): a fake ``webview`` in ``sys.modules``, the lifetime through ``cli.ui``, the session hook."""
import inspect
import signal
import sys
import threading
import time
import types
import urllib.request

import pytest

from castlib import cli, platform, window, window_probe
from castlib.platform import SessionEnd
from castlib.sources.local import item_for_path
from tests.conftest import wait_for


class FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self, *args):
        """Call each handler as pywebview does: with as many of ``args`` as it takes; their answers."""
        return [h(*args[:len(inspect.signature(h).parameters)]) for h in self.handlers]


class FakeWindow:
    def __init__(self, fake, title, url, kw):
        self.fake, self.title, self.url, self.kw = fake, title, url, kw
        self.events = types.SimpleNamespace(**{name: FakeEvent() for name in (
            "initialized", "shown", "loaded", "minimized", "restored", "maximized", "closed")})
        self.is_shown = False
        self.destroys = 0
        self.gone = threading.Event()
        self.calls = []

    def evaluate_js(self, script):
        self.calls.append(("evaluate_js", script))
        answer = self.fake.page.get(script)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def destroy(self):
        if not self.is_shown:
            self.fake.errors.append("destroy() before shown: pywebview would wait 20 s for it")
        self.destroys += 1
        self.gone.set()

    def restore(self):
        self.calls.append("restore")

    @property
    def on_top(self):
        return False

    @on_top.setter
    def on_top(self, value):
        self.calls.append(("on_top", value))


class FakeWebview(types.ModuleType):
    """pywebview's surface that ``castlib.window`` uses, with the order of ``webview.start()`` kept.

    ``start()`` sets ``renderer`` and fires ``initialized(renderer)`` first; a
    handler answering False cancels the window and ``start()`` returns with none
    (webview/window.py:212, webview/__init__.py:276-279). Then, optionally held
    by ``show_gate`` or failing with ``fail``, the window is shown, and ``start()``
    blocks until the window is destroyed - or returns at once when
    ``user_closes`` (the person pressed X).
    """

    def __init__(self):
        super().__init__("webview")
        self.renderer = None
        self.engine = "edgechromium"
        self.windows = []
        self.errors = []
        self.fail = None
        self.show_gate = None
        self.user_closes = False
        self.on_create = None
        self.created = threading.Event()
        self.on_shown = threading.Event()
        self.gui = "not started"
        self.page = {"document.title": "cast-tv", "typeof window.Alpine": "object"}   # what evaluate_js answers
        self.loads = True                    # False: the page never fires loaded

    def create_window(self, title, url, **kw):
        if self.on_create is not None:
            self.on_create()
        w = FakeWindow(self, title, url, kw)
        self.windows.append(w)
        return w

    def start(self, func=None, gui=None, **kw):
        self.gui = gui
        w = self.windows[-1]
        self.renderer = self.engine
        if any(answer is False for answer in w.events.initialized.fire(self.engine)):
            return
        self.created.set()
        if self.show_gate is not None:
            assert self.show_gate.wait(5)
        if self.fail is not None:
            raise self.fail
        w.is_shown = True
        w.events.shown.fire()
        self.on_shown.set()
        if self.loads:
            w.events.loaded.fire()
        if self.user_closes:
            return
        assert w.gone.wait(5), "the window was never destroyed"


class WebViewException(Exception):
    pass


@pytest.fixture
def fake_webview(monkeypatch):
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(window, "expected_renderer", lambda: "edgechromium")
    monkeypatch.setattr(window, "STEP", 0.01)
    monkeypatch.setenv("PYWEBVIEW_GUI", "qt")        # _webview() writes it on Linux; put back afterwards
    monkeypatch.delenv(window.FAIL_ENV, raising=False)
    return fake


def _in_thread(fn):
    t = threading.Thread(target=fn, daemon=True)
    t.start()
    return t


def _closers():
    return [t for t in threading.enumerate() if t.name == "window-closer"]


# ------------------------------------------------------------------ the module
def test_expected_renderer_per_platform(monkeypatch):
    for plat, renderer in (("win32", "edgechromium"), ("linux", "qtwebengine"), ("darwin", None)):
        monkeypatch.setattr(window, "sys", types.SimpleNamespace(platform=plat))
        assert window.expected_renderer() == renderer


def test_window_opens_the_ui_and_closes(fake_webview):
    fake_webview.user_closes = True
    before = signal.getsignal(signal.SIGINT)
    assert window.run(object(), "http://127.0.0.1:8895/ui/") == "closed"
    (w,) = fake_webview.windows
    assert w.title == "cast-tv" and w.url == "http://127.0.0.1:8895/ui/"
    assert fake_webview.gui == ("qt" if sys.platform.startswith("linux") else None)
    assert signal.getsignal(signal.SIGINT) is before      # the tab path gets Python's Ctrl+C back
    assert not window.exists() and not window.show()
    assert fake_webview.errors == [] and _closers() == []


def test_wrong_renderer_falls_back(fake_webview):
    """pywebview's quiet fallback (MSHTML without WebView2) is refused before any window appears."""
    fake_webview.engine = "mshtml"
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "unavailable: the mshtml engine loaded, not edgechromium"
    assert not fake_webview.created.is_set() and not fake_webview.windows[0].is_shown


def test_missing_backend_falls_back(fake_webview, monkeypatch):
    fake_webview.fail = WebViewException("You must have pythonnet installed in order to use pywebview.")
    assert window.run(object(), "http://127.0.0.1:1/ui/") == (
        "unavailable: You must have pythonnet installed in order to use pywebview.")
    monkeypatch.setitem(sys.modules, "webview", None)          # pipx without the window extra
    assert not window.installed()
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "unavailable: pywebview is not installed"
    assert window.describe() == "Window: none (pywebview is not installed)"
    assert _closers() == []


def test_forced_fallback_opens_no_window(fake_webview, monkeypatch):
    monkeypatch.setenv(window.FAIL_ENV, "1")
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "unavailable: CAST_TV_WINDOW_FAIL"
    assert fake_webview.windows == []


# ------------------------------------------------------------ --window-check
def test_window_check_reads_the_page_back(fake_webview):
    """The release smoke test's probe: the expected engine, the page's title, Alpine running; then closed."""
    assert window_probe.check("http://127.0.0.1:1/ui/", timeout=1) == "window-check: edgechromium OK"
    w = fake_webview.windows[0]
    assert w.url == "http://127.0.0.1:1/ui/" and w.title == "cast-tv" and w.destroys == 1
    assert ("evaluate_js", "document.title") in w.calls and fake_webview.errors == []


def test_window_check_refuses_the_wrong_engine(fake_webview):
    """MSHTML instead of WebView2 renders a page too; the check must still fail, with no window shown."""
    fake_webview.engine = "mshtml"
    with pytest.raises(RuntimeError, match="the mshtml engine loaded, not edgechromium"):
        window_probe.check("http://127.0.0.1:1/ui/", timeout=1)
    assert not fake_webview.windows[0].is_shown


@pytest.mark.parametrize("page, says", [
    ({"document.title": "cast-tv", "typeof window.Alpine": "undefined"}, "Alpine 'undefined'"),
    ({"document.title": "404", "typeof window.Alpine": "object"}, "document.title '404'"),
    ({"typeof window.Alpine": RuntimeError("JavaScript is off")}, "JavaScript is off"),
])
def test_window_check_fails_when_the_page_did_not_run(fake_webview, page, says):
    fake_webview.page = page
    with pytest.raises(RuntimeError, match=says):
        window_probe.check("http://127.0.0.1:1/ui/", timeout=0.3)
    assert fake_webview.windows[0].destroys == 1


def test_window_check_gives_up_on_a_page_that_never_loads(fake_webview, monkeypatch):
    monkeypatch.setattr(window_probe, "GRACE", 0.1)
    fake_webview.loads = False
    with pytest.raises(RuntimeError, match="did not load within"):
        window_probe.check("http://127.0.0.1:1/ui/", timeout=0.1)


def test_window_check_without_the_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", None)
    monkeypatch.setattr(window, "expected_renderer", lambda: "edgechromium")
    with pytest.raises(RuntimeError, match="pywebview is not installed"):
        window_probe.check("http://127.0.0.1:1/ui/")


def test_window_check_command_serves_the_ui_and_ends(fake_webview, capsys):
    """``cast-tv --window-check`` serves /ui/ on a spare loopback port, prints the line, exits 0; 1 on a failure."""
    served = []

    def opened():
        served.append(fake_webview.windows[-1].url)
        with urllib.request.urlopen(served[-1], timeout=5) as r:
            served.append(r.status)

    original = fake_webview.start

    def start(*a, **kw):
        opened()
        return original(*a, **kw)

    fake_webview.start = start
    assert cli.main_tv(["--window-check"]) == 0
    assert capsys.readouterr().out.strip() == "window-check: edgechromium OK"
    assert served[0].startswith("http://127.0.0.1:") and served[0].endswith("/ui/") and served[1] == 200
    fake_webview.engine = "mshtml"
    assert cli.main_tv(["--window-check"]) == 1
    assert capsys.readouterr().out.strip() == "window-check failed: the mshtml engine loaded, not edgechromium"


@pytest.mark.parametrize("fails", [False, True])
def test_end_during_backend_import_stops_without_fallback(window_cli, monkeypatch, fails):
    def importing():
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        if fails:
            raise ImportError("backend unavailable")
        return window_cli.fake

    monkeypatch.setattr(window, "_webview", importing)
    assert cli.ui(port=window_cli.app.server.port) == 0
    assert window_cli.stops == ["interrupted"] and window_cli.app._closed.is_set()
    assert window_cli.app.tv_fake.actions().count("Stop") == 1
    assert window_cli.tabs == [] and window_cli.served == [] and window_cli.fake.windows == []
    assert _closers() == [] and not window.exists()


@pytest.mark.parametrize("source", ["sigterm", "console", "session"])
def test_end_during_hook_setup_stops_without_a_window(window_cli, monkeypatch, source):
    def console(on_end):
        if source == "console" and on_end is not None:
            on_end()

    def session(on_end):
        if source == "sigterm":
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        elif source == "session":
            on_end(time.monotonic() + SessionEnd.DEADLINE)
        return None

    monkeypatch.setattr(platform, "console_close_ends", console)
    monkeypatch.setattr(platform, "end_on_session_end", session)
    assert cli.ui(port=window_cli.app.server.port) == 0
    assert window_cli.stops == ["interrupted"] and window_cli.app._closed.is_set()
    assert window_cli.app.tv_fake.actions().count("Stop") == 1
    assert window_cli.tabs == [] and window_cli.served == [] and window_cli.fake.windows == []
    assert _closers() == [] and not window.exists()


def test_direct_run_retains_end_during_import_and_clears_it(fake_webview, monkeypatch):
    original = window._webview

    def importing():
        window.destroy()
        raise ImportError("backend unavailable")

    monkeypatch.setattr(window, "_webview", importing)
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "closed"
    monkeypatch.setattr(window, "_webview", original)
    fake_webview.user_closes = True
    window.destroy()  # outside the scope: must not poison the next run
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "closed"
    assert len(fake_webview.windows) == 1 and _closers() == []


def test_hook_setup_exception_clears_termination_state(window_cli, monkeypatch):
    def session(on_end):
        window.destroy()
        raise RuntimeError("hook failed")

    monkeypatch.setattr(platform, "end_on_session_end", session)
    with pytest.raises(RuntimeError, match="hook failed"):
        cli.ui(port=window_cli.app.server.port)
    handler = signal.getsignal(signal.SIGTERM)
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGTERM, None)
    window_cli.fake.user_closes = True
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "closed"
    assert len(window_cli.fake.windows) == 1 and _closers() == []


def test_destroy_while_starting_waits_for_shown(fake_webview):
    """A kill between create_window and shown returns at once, and the window is destroyed only once shown."""
    fake_webview.show_gate = threading.Event()
    seen = {}

    def kill_while_starting():
        assert fake_webview.created.wait(5)
        t0 = time.perf_counter()
        for _ in range(3):                                     # repeated requests: one destroy
            window.destroy()
        seen["took"] = time.perf_counter() - t0
        time.sleep(0.1)
        seen["early"] = fake_webview.windows[0].destroys
        fake_webview.show_gate.set()
    t = _in_thread(kill_while_starting)
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "closed"
    t.join(5)
    assert seen["took"] < 0.05 and seen["early"] == 0
    assert fake_webview.windows[0].destroys == 1
    assert fake_webview.errors == [] and _closers() == []


def test_destroy_before_the_window_exists(fake_webview):
    fake_webview.on_create = window.destroy                    # the request lands before create_window
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "closed"
    assert fake_webview.windows[0].destroys == 1 and fake_webview.errors == []


def test_failed_start_with_a_pending_end_is_closed(fake_webview):
    """The end was asked for: the CLI stops and closes the app instead of opening a tab."""
    fake_webview.show_gate = threading.Event()
    fake_webview.fail = WebViewException("Main window failed to start")

    def kill_then_fail():
        assert fake_webview.created.wait(5)
        window.destroy()
        fake_webview.show_gate.set()
    t = _in_thread(kill_then_fail)
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "closed"
    t.join(5)
    assert _closers() == []                                    # no worker left waiting


def test_failed_start_without_a_request_is_unavailable(fake_webview):
    fake_webview.fail = WebViewException("Main window failed to start")
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "unavailable: Main window failed to start"
    assert _closers() == []


def test_end_requested_beats_a_wrong_renderer(fake_webview):
    fake_webview.engine = "mshtml"
    fake_webview.on_create = window.destroy
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "closed"


def test_show_brings_the_window_forward(fake_webview):
    assert window.show() is False                              # no window: a second launch opens a tab
    window.destroy()                                           # outside run(): nothing to do
    answers = {}

    def second_launch():
        assert fake_webview.on_shown.wait(5)
        w = fake_webview.windows[0]
        answers["exists"] = window.exists()
        answers["plain"] = (window.show(), list(w.calls))
        w.calls.clear()
        w.events.minimized.fire()
        answers["minimized"] = (window.show(), list(w.calls))
        window.destroy()
    t = _in_thread(second_launch)
    assert window.run(object(), "http://127.0.0.1:1/ui/") == "closed"
    t.join(5)
    assert answers["exists"] is True
    assert answers["plain"] == (True, [("on_top", True), ("on_top", False)])
    assert answers["minimized"] == (True, ["restore", ("on_top", True), ("on_top", False)])


# ---------------------------------------------------------- the lifetime through cli.ui
@pytest.fixture
def window_cli(app, fake_webview, monkeypatch, tmp_path):
    """``cli.ui`` on the ``app`` fixture (a FakeTV) with a video playing; ``App.start``'s arguments are recorded."""
    started = {}

    def start(cls, port, **kw):
        started.update(kw, port=port)
        return app
    monkeypatch.setattr(cli.App, "start", classmethod(start))
    tabs, served = [], []
    monkeypatch.setattr(app, "open_tab", lambda: tabs.append(True))
    monkeypatch.setattr(app, "run_forever", lambda: served.append(True) or 0)   # the tab path; never blocks a test
    app.tv_fake.video_script = ["PLAYING"]
    clip = tmp_path / "film.mp4"
    clip.write_bytes(b"\0" * 100)
    cast = app.cast(item_for_path(str(clip)))
    assert cast.sent.wait(5)
    calls = []
    real_interrupted = app.interrupted
    monkeypatch.setattr(app, "interrupted", lambda: calls.append("interrupted") or real_interrupted())
    before = signal.getsignal(signal.SIGTERM)
    try:
        yield types.SimpleNamespace(app=app, fake=fake_webview, started=started, tabs=tabs, stops=calls,
                                    served=served)
    finally:
        signal.signal(signal.SIGTERM, before)


def test_gui_end_stops_and_closes(window_cli, capsys):
    """X on the window: the TV stops, the app closes, no tab; the Google consent may still open a browser."""
    window_cli.fake.user_closes = True
    assert cli.ui(port=window_cli.app.server.port) == 0
    assert window_cli.started["open_ui"] is False and window_cli.started["browser"] is True
    assert window_cli.started["ends"] == cli.WINDOW_ENDS
    assert window_cli.app.tv_fake.actions().count("Stop") == 1
    assert window_cli.app._closed.is_set() and window_cli.stops == ["interrupted"]
    assert window_cli.tabs == [] and window_cli.served == []
    assert "Stopped." in capsys.readouterr().out
    # row 2.6: a Ctrl+C landing now would break pythonnet's atexit unload with a traceback
    assert signal.getsignal(signal.SIGINT) is signal.SIG_IGN


def test_sigterm_destroys_window(window_cli):
    """A kill on Fedora: the handler destroys the window, and the GUI loop's return stops the TV."""
    def kill():
        assert window_cli.fake.on_shown.wait(5)
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    t = _in_thread(kill)
    assert cli.ui(port=window_cli.app.server.port) == 0
    t.join(5)
    assert window_cli.fake.windows[0].destroys == 1
    assert window_cli.app.tv_fake.actions().count("Stop") == 1 and window_cli.app._closed.is_set()
    assert window_cli.tabs == [] and window_cli.served == [] and window_cli.fake.errors == []
    handler = signal.getsignal(signal.SIGTERM)
    with pytest.raises(KeyboardInterrupt):                     # back to Ctrl+C's way once the window is gone
        handler(signal.SIGTERM, None)


def test_sigterm_while_the_window_starts_stops_once(window_cli):
    window_cli.fake.show_gate = threading.Event()

    def kill():
        assert window_cli.fake.created.wait(5)
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        time.sleep(0.05)
        window_cli.fake.show_gate.set()
    t = _in_thread(kill)
    assert cli.ui(port=window_cli.app.server.port) == 0
    t.join(5)
    assert window_cli.stops == ["interrupted"] and window_cli.tabs == []
    assert window_cli.app.tv_fake.actions().count("Stop") == 1 and window_cli.fake.errors == []


def test_console_close_destroys_window(window_cli, monkeypatch):
    ends = []
    monkeypatch.setattr(platform, "console_close_ends", ends.append)
    window_cli.fake.user_closes = True
    assert cli.ui(port=window_cli.app.server.port) == 0
    assert ends == [window.destroy, None]                      # the window's destroy while it is up, then Ctrl+C's way


def test_quit_closes_the_window(window_cli):
    def quit_from_the_ui():
        assert window_cli.fake.on_shown.wait(5)
        window_cli.app.quit()
    t = _in_thread(quit_from_the_ui)
    assert cli.ui(port=window_cli.app.server.port) == 0
    t.join(5)
    assert window_cli.stops == ["interrupted"] and window_cli.app._closed.is_set()


def test_unavailable_window_opens_the_tab(window_cli, monkeypatch, capsys):
    monkeypatch.setenv(window.FAIL_ENV, "1")
    shown = []
    monkeypatch.setattr(platform, "show_console", lambda: shown.append(True) or True)
    before = signal.getsignal(signal.SIGINT)
    assert cli.ui(port=window_cli.app.server.port) == 0
    assert shown == [True], "the console hidden at start must come back next to the tab"
    assert signal.getsignal(signal.SIGINT) is before          # the tab still ends on Ctrl+C
    assert window_cli.tabs == [True] and window_cli.served == [True] and window_cli.stops == []
    (err,) = window_cli.app.errors.list()
    assert err["code"] == "window_unavailable" and "CAST_TV_WINDOW_FAIL" in err["message"]
    out = capsys.readouterr().out
    assert "No cast-tv window (CAST_TV_WINDOW_FAIL)" in out and "Ctrl+C ends it" in out


def test_no_window_flag_keeps_the_tab(window_cli, monkeypatch):
    assert cli.ui(port=window_cli.app.server.port, windowed=False) == 0
    assert window_cli.started["open_ui"] is True and window_cli.served == [True]
    assert window_cli.fake.windows == []


def test_no_browser_opens_neither_window_nor_consent(window_cli, monkeypatch):
    assert cli.ui(port=window_cli.app.server.port, browser=False) == 0
    assert window_cli.started["browser"] is False and window_cli.started["open_ui"] is False
    assert window_cli.fake.windows == [] and window_cli.tabs == []


# ------------------------------------------------------------- Windows sign-out
class FakeNative:
    def __init__(self, ok=True):
        self.ok = ok
        self.started = None
        self.stopped = 0

    def window_procedure(self, handle):
        return lambda msg, wparam: handle(msg, wparam)

    def start(self, procedure):
        self.started = procedure
        return self.ok

    def stop(self):
        self.stopped += 1


QUERY, END = SessionEnd.WM_QUERYENDSESSION, SessionEnd.WM_ENDSESSION


def test_session_query_and_cancel_keep_playing():
    ended = []
    hook = SessionEnd(lambda deadline: ended.append(True), native=FakeNative())
    assert hook.handle(QUERY, 0) == 1                          # yes, without cleaning up: it may be cancelled
    assert hook.handle(END, 0) == 0                            # cancelled
    assert hook.handle(0x0001, 0) is None                      # anything else: DefWindowProc
    assert ended == []


def test_session_end_runs_once():
    ended = []
    hook = SessionEnd(lambda deadline: ended.append(deadline), native=FakeNative())
    assert hook.handle(END, 1) == 0
    assert hook.handle(END, 1) == 0
    assert len(ended) == 1 and time.monotonic() < ended[0] <= time.monotonic() + SessionEnd.DEADLINE


def test_session_end_waits_within_the_deadline():
    """A TV that never answers Stop: the callback gives up after 4 s in all, counted from the first message."""
    clock = [100.0]
    waits = []

    def wait(event, timeout):
        waits.append(timeout)
        clock[0] += timeout
        return event.is_set()
    stalled = threading.Event()
    deadlines = []

    def cleanup(deadline):
        deadlines.append(deadline)
        stalled.wait(5)

    hook = SessionEnd(cleanup, native=FakeNative(), clock=lambda: clock[0], wait=wait)
    assert hook.end() is False
    assert waits == [SessionEnd.DEADLINE] and SessionEnd.DEADLINE <= 4
    assert hook.end() is False                                 # repeated: the budget is spent, no second wait
    assert waits == [SessionEnd.DEADLINE]
    stalled.set()
    assert hook._done.wait(1) and deadlines == [104.0]  # same absolute deadline, even if the worker ran later
    quick = SessionEnd(lambda deadline: stalled.wait(5) and time.sleep(5), native=FakeNative(), deadline=0.2)
    t0 = time.perf_counter()
    assert quick.handle(END, 1) == 0
    assert time.perf_counter() - t0 < 1.5


def test_session_hook_registration_and_release():
    native = FakeNative()
    hook = SessionEnd(lambda deadline: None, native=native)
    assert hook.install() is True
    assert hook._callback is native.started and hook._callback(QUERY, 0) == 1   # kept alive while registered
    hook.release()
    hook.release()
    assert native.stopped == 1 and hook._callback is None
    failing = SessionEnd(lambda deadline: None, native=FakeNative(ok=False))
    assert failing.install() is False and failing._callback is None


def test_session_end_races_the_gui_teardown(window_cli, monkeypatch):
    """A sign-out with the window open: the hook and the GUI loop's return both stop; Stop goes out once."""
    hooks = []

    def install(on_end):
        hook = SessionEnd(on_end, native=FakeNative())
        hook.install()
        hooks.append(hook)
        return hook
    monkeypatch.setattr(platform, "end_on_session_end", install)
    answered = []

    def sign_out():
        assert window_cli.fake.on_shown.wait(5)
        assert hooks[0].handle(QUERY, 0) == 1
        answered.append(hooks[0].handle(END, 1))
    t = _in_thread(sign_out)
    assert cli.ui(port=window_cli.app.server.port) == 0
    t.join(5)
    assert answered == [0] and hooks[0]._callback is None      # released with the window
    assert window_cli.stops == ["interrupted"]
    assert window_cli.app.tv_fake.actions().count("Stop") == 1 and window_cli.app._closed.is_set()


def test_gui_interrupt_racing_quit_stops_once(window_cli, monkeypatch):
    def interrupted_start(**kwargs):
        window_cli.app.quit()
        raise KeyboardInterrupt

    monkeypatch.setattr(window_cli.fake, "start", interrupted_start)
    assert cli.ui(port=window_cli.app.server.port) == 0
    assert window_cli.stops == ["interrupted"] and window_cli.app._close_done.is_set()
    assert window_cli.app.tv_fake.actions().count("Stop") == 1


def test_tab_interrupt_racing_quit_stops_once(window_cli, monkeypatch):
    from castlib import app as app_module

    def interrupted_install():
        window_cli.app.quit()
        raise KeyboardInterrupt

    monkeypatch.setattr(app_module, "end_on_sigterm", interrupted_install)
    # The fixture normally replaces run_forever so a fallback cannot block.
    assert app_module.App.run_forever(window_cli.app) == 0
    assert window_cli.stops == ["interrupted"] and window_cli.app._close_done.is_set()
    assert window_cli.app.tv_fake.actions().count("Stop") == 1


@pytest.mark.parametrize("ordinary_first", [False, True])
def test_session_deadline_reaches_cleanup_despite_stalled_stop(window_cli, monkeypatch, ordinary_first):
    """A stalled Stop and source must not starve cancellation, other sources or either server close call."""
    from castlib import dlna

    app = window_cli.app
    release = threading.Event()
    stopping = threading.Event()
    stop_returned = threading.Event()
    source_returned = threading.Event()
    calls = []
    soap = dlna.soap

    def stalled_soap(avt, service, action, *args, **kwargs):
        if action != "Stop":
            return soap(avt, service, action, *args, **kwargs)
        calls.append("Stop")
        stopping.set()
        try:
            assert release.wait(5)
        finally:
            stop_returned.set()

    def first_source():
        calls.append("first source")
        try:
            assert release.wait(5)
        finally:
            source_returned.set()

    monkeypatch.setattr(dlna, "soap", stalled_soap)
    app.sources = {"first": types.SimpleNamespace(close=first_source),
                   "second": types.SimpleNamespace(close=lambda: calls.append("second source"))}
    shutdown, server_close = app.server.shutdown, app.server.server_close
    monkeypatch.setattr(app.server, "shutdown", lambda: calls.append("server shutdown") or shutdown())
    monkeypatch.setattr(app.server, "server_close", lambda: calls.append("server close") or server_close())
    hooks = []

    def install(on_end):
        hook = SessionEnd(on_end, native=FakeNative(), deadline=0.6)
        hook.install()
        hooks.append(hook)
        return hook

    monkeypatch.setattr(platform, "end_on_session_end", install)
    answered = []

    def sign_out():
        assert window_cli.fake.on_shown.wait(5)
        if ordinary_first:
            app.quit()
            assert stopping.wait(5)
        started = time.monotonic()
        hooks[0].handle(END, 1)
        hooks[0].handle(END, 1)  # the budget and attempts must not restart
        answered.append(time.monotonic() - started)

    t = _in_thread(sign_out)
    try:
        assert cli.ui(port=app.server.port) == 0
        t.join(2)
        assert answered and answered[0] < 1.2
        assert not release.is_set() and app.current.terminal
        assert calls.count("Stop") == 1
        for name in ("first source", "second source", "server shutdown", "server close"):
            assert calls.count(name) == 1
        assert window_cli.stops == ["interrupted"] and window_cli.tabs == []
        assert app._closed.is_set() and window_cli.fake.windows[0].destroys == 1
    finally:
        release.set()
        t.join(5)
        assert stop_returned.wait(5) and source_returned.wait(5)
        assert app._shut_down.wait(5)
        wait_for(lambda: not any(worker.name == "shutdown-action" for worker in threading.enumerate()))


@pytest.mark.skipif(sys.platform != "win32", reason="a real hidden window needs user32")
def test_session_hook_with_a_real_hidden_window():
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.WinDLL("user32")
    u32.SendMessageW.restype = ctypes.c_ssize_t
    u32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    ended = []
    hook = SessionEnd(lambda deadline: ended.append(True), deadline=1)
    assert hook.install() is True
    native = hook._native
    try:
        hwnd = native._hwnd
        assert hwnd and not u32.IsWindowVisible(hwnd)
        assert u32.SendMessageW(hwnd, QUERY, 0, 0) == 1
        assert u32.SendMessageW(hwnd, END, 0, 0) == 0 and ended == []
        assert u32.SendMessageW(hwnd, END, 1, 0) == 0 and ended == [True]
    finally:
        hook.release()
    assert not native._thread.is_alive() and hook._callback is None
    wait_for(lambda: not u32.IsWindow(hwnd))
