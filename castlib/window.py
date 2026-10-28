"""The cast-tv window: the UI in a native webview that owns the session.

pywebview with WebView2 on Windows and Qt WebEngine on Linux, from the
optional ``window`` extra. ``webview`` is imported inside the functions only:
the core install has no extra, the CLI imports this module anyway, and the
tests put a fake in ``sys.modules``.

One window per process. ``run()`` parks the main thread in the GUI loop until
the window closes; ``destroy()`` and ``show()`` reach it from any thread, a
signal handler included. ``destroy()`` only records the request, without a
lock: pywebview's own ``Window.destroy()`` waits up to 20 s for the window to
be shown, so a worker calls it once the window is shown.

pywebview falls back to another engine quietly when the requested one fails
to load (WebView2 missing gives MSHTML; a broken Qt gives GTK), so a rendered
page proves nothing: the engine is checked in ``events.initialized``, which
cancels the window before it appears (owner decision 2026-10-18).
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import signal
import sys
import threading
import time
from contextlib import contextmanager

TITLE = "cast-tv"
SIZE = (1180, 820)
MIN_SIZE = (420, 480)
FAIL_ENV = "CAST_TV_WINDOW_FAIL"   # test-only: run() answers unavailable before any window
STEP = 0.05                        # seconds the closer sleeps between looks at the request


def expected_renderer() -> str | None:
    """The engine a cast-tv window must run on here; anything else counts as no window."""
    if sys.platform == "win32":
        return "edgechromium"
    if sys.platform.startswith("linux"):
        return "qtwebengine"
    return None


def installed() -> bool:
    """Whether the ``window`` extra is installed on a platform that has a window; nothing is imported."""
    if expected_renderer() is None:
        return False
    if "webview" in sys.modules:
        return sys.modules["webview"] is not None
    try:
        return importlib.util.find_spec("webview") is not None
    except (ImportError, ValueError):
        return False


def _webview():
    if sys.platform.startswith("linux"):
        os.environ["PYWEBVIEW_GUI"] = "qt"       # a host GTK is never picked
    import webview
    return webview


def _backend_module() -> str:
    return "webview.platforms.winforms" if sys.platform == "win32" else "webview.platforms.qt"


def _reason(err: BaseException) -> str:
    if isinstance(err, ImportError) and getattr(err, "name", None) == "webview":
        return "pywebview is not installed"
    return str(err) or type(err).__name__


def describe() -> str:
    """The ``--version`` line: the engine a window would load, or why there is none. Opens nothing.

    Importing the backend module is what makes pywebview choose: on Windows it
    looks for the WebView2 runtime there and settles on MSHTML without it.
    """
    expected = expected_renderer()
    if expected is None:
        return "Window: none (no window on this platform)"
    try:
        _webview()
        backend = importlib.import_module(_backend_module())
    except Exception as e:
        return "Window: none (%s)" % _reason(e)
    renderer = getattr(backend, "renderer", None)
    if renderer != expected:
        return "Window: none (the %s engine would load, not %s)" % (renderer, expected)
    return "Window: %s" % renderer


class _Run:
    """One ``run()``: plain attributes, so a signal handler can write them without taking a lock."""

    def __init__(self):
        self.window = None          # pywebview's Window, until the run ends
        self.shown = False
        self.minimized = False
        self.end_requested = False  # destroy() asked; kept through the window's creation
        self.finished = False       # run() is returning: the closer stops waiting
        self.rejected: str | None = None


_current: _Run | None = None


@contextmanager
def termination_scope():
    """Retain end requests before installing handlers, through backend loading and GUI teardown.

    The CLI owns the outer scope; direct run() callers get one automatically.
    Nested scopes share the request and only the outer scope clears it.
    """
    global _current
    owns = _current is None
    if owns:
        _current = _Run()
    try:
        yield _current
    finally:
        if owns:
            _current.finished = True
            _current.window = None
            _current = None


def _closer(run: _Run) -> None:
    """Destroy the window once it is shown and someone asked; never before, never twice."""
    while not run.finished:
        if run.end_requested and run.shown:
            try:
                run.window.destroy()
            except Exception:
                pass
            return
        time.sleep(STEP)


def run(app, url: str, on_shown=None) -> str:
    """Show ``url`` (the UI of ``app``) in the cast-tv window until it closes; the main thread only.

    ``on_shown()`` is called once the window is on screen, on the GUI thread.
    Returns ``"closed"`` when the window was closed or destroyed, or
    ``"unavailable: <reason>"`` when no window could open or the engine was
    the wrong one. Either way ``app`` still runs; the caller stops it or opens
    the browser tab instead. A ``destroy()`` that came while the window was
    starting wins over a failure to start: the answer is then ``"closed"``.
    """
    with termination_scope() as current:
        result = _run(current, url, on_shown)
        return "closed" if current.end_requested else result


def _run(current: _Run, url: str, on_shown=None) -> str:
    if current.end_requested:
        return "closed"
    if os.environ.get(FAIL_ENV) == "1":
        return "unavailable: " + FAIL_ENV
    expected = expected_renderer()
    if expected is None:
        return "unavailable: no window on this platform"
    try:
        webview = _webview()
    except Exception as e:
        return "unavailable: %s" % _reason(e)

    if current.end_requested:
        return "closed"

    def check(renderer):
        if renderer != expected:
            current.rejected = "the %s engine loaded, not %s" % (renderer, expected)
            return False                         # pywebview cancels the window and the GUI loop
        return True

    def shown():
        current.shown = True
        if on_shown is not None:
            try:
                on_shown()
            except Exception:
                pass                             # a failed message must not take the window down

    def minimized():
        current.minimized = True

    def restored():
        current.minimized = False

    closer = threading.Thread(target=_closer, args=(current,), name="window-closer", daemon=True)
    interrupt = signal.getsignal(signal.SIGINT)  # both backends install their own; the tab path needs Python's back
    failure = None
    try:
        window = webview.create_window(TITLE, url, width=SIZE[0], height=SIZE[1], min_size=MIN_SIZE)
        current.window = window
        window.events.initialized += check
        window.events.shown += shown
        window.events.minimized += minimized
        window.events.restored += restored
        window.events.maximized += restored
        closer.start()
        webview.start(gui="qt" if sys.platform.startswith("linux") else None)
    except Exception as e:
        failure = _reason(e)
    finally:
        current.finished = True
        if closer.is_alive():
            closer.join(1)
        current.window = None
        try:
            signal.signal(signal.SIGINT, interrupt)
        except (ValueError, OSError, TypeError):
            pass
    if current.end_requested:
        return "closed"
    if current.rejected:
        return "unavailable: " + current.rejected
    if failure:
        return "unavailable: " + failure
    if not current.shown:
        return "unavailable: the window never opened"
    return "closed"


def exists() -> bool:
    """A cast-tv window is on screen in this process."""
    current = _current
    return current is not None and current.shown and not current.finished


def show() -> bool:
    """Bring the window to the front: restored when minimized, then briefly on top. False with no window."""
    current = _current
    if current is None or not current.shown or current.end_requested or current.finished:
        return False
    window = current.window
    if window is None:
        return False
    try:
        if current.minimized:
            window.restore()
        window.on_top = True
        window.on_top = False
    except Exception:
        return False
    return True


def destroy() -> None:
    """Ask the window to close; idempotent, a no-op outside its termination scope.

    Only a flag is written: the closer destroys the window once it is shown,
    and ``run()`` answers ``"closed"`` even if the window never came up.
    """
    current = _current
    if current is not None:
        current.end_requested = True
