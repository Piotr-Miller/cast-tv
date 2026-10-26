"""``cast-tv --window-check``: the release smoke test opens the cast-tv window and reads the page back.

A rendered page alone proves nothing, since pywebview falls back to another
engine quietly (``castlib.window``). The probe passes only when the expected
engine loaded, ``document.title`` is ``cast-tv`` and Alpine ran. It lives
apart from ``castlib.window``, whose ``run()`` owns the session: the probe
owns nothing and ends by itself.
"""
from __future__ import annotations

import sys
import threading
import time

from castlib import window

TIMEOUT = 60       # seconds the probe waits for Alpine; a cold onefile start is slow
GRACE = 10         # and a little more before it gives up on a page that never loaded


def check(url: str, timeout: float = TIMEOUT) -> str:
    """Open ``url`` in a cast-tv window, read back the page, close it: the ``--window-check`` line.

    Raises ``RuntimeError`` with what was seen when the engine, the title or
    Alpine is not what the release needs.
    """
    expected = window.expected_renderer()
    if expected is None:
        raise RuntimeError("no window on this platform")
    try:
        webview = window._webview()
    except Exception as e:
        raise RuntimeError(window._reason(e)) from e
    seen = {}
    probing = threading.Lock()

    def initialized(renderer):
        seen["renderer"] = renderer
        return renderer == expected              # the wrong engine never shows a window

    def probe():
        if not probing.acquire(blocking=False):  # loaded fires again on every navigation
            return
        try:
            until = time.monotonic() + timeout
            while win.evaluate_js("typeof window.Alpine") != "object" and time.monotonic() < until:
                time.sleep(0.25)                 # Alpine is deferred: it runs after "loaded"
            seen["title"] = win.evaluate_js("document.title")
            seen["alpine"] = win.evaluate_js("typeof window.Alpine")
        except Exception as e:
            seen["error"] = window._reason(e)
        finally:
            win.destroy()

    def give_up():
        seen.setdefault("error", "the page did not load within %g s" % timeout)
        win.destroy()

    win = webview.create_window(window.TITLE, url, width=window.SIZE[0], height=window.SIZE[1],
                                min_size=window.MIN_SIZE)
    win.events.initialized += initialized
    win.events.loaded += lambda: threading.Thread(target=probe, name="window-check", daemon=True).start()
    watchdog = threading.Timer(timeout + GRACE, give_up)
    watchdog.daemon = True
    watchdog.start()
    try:
        webview.start(gui="qt" if sys.platform.startswith("linux") else None)
    except Exception as e:
        raise RuntimeError(window._reason(e)) from e
    finally:
        watchdog.cancel()
    renderer = seen.get("renderer")
    if renderer != expected:
        raise RuntimeError("the %s engine loaded, not %s" % (renderer, expected))
    if "error" in seen:
        raise RuntimeError(seen["error"])
    if seen.get("title") != window.TITLE or seen.get("alpine") != "object":
        raise RuntimeError("the page did not run: document.title %r, Alpine %r" % (
            seen.get("title"), seen.get("alpine")))
    return "window-check: %s OK" % renderer
