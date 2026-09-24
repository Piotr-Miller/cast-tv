"""The GoPro hand-off: a gopro.com window in a browser cast-tv launches and owns, read over DevTools.

The GoPro tab's token used to be copied out of the browser's devtools by hand.
Instead, cast-tv launches a Chromium-family browser already on this computer
(Chrome, Chromium, Edge, Brave) with a profile of its own under
``config_dir()`` and a random local DevTools port, opens gopro.com in it, and
waits for the person to sign in there the way they normally do. It then reads
the ``gp_access_token`` cookie of that session over the DevTools Protocol
(``castlib.auth.cdp``), hands each distinct value to a ``verify`` callback
once (the source proves it against ``api.gopro.com``; finding a cookie is not
success), and closes the window on the first value that verifies. The person's
own browser and its profile are never touched: a fresh ``--user-data-dir`` is
a separate browser process.

Only Chromium-family browsers speak the protocol (Firefox removed it in 141),
and Chrome ignores ``--remote-debugging-port`` on its default profile since
136, so the private profile is a requirement as much as a design choice.
``CAST_TV_BROWSER`` names the executable to use and is then the only
candidate, tried even when the file is missing, so a failure is reported
rather than hidden (the ``GOOGLE_CLIENT_JSON`` rule). Nothing here prints or
logs a cookie value.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time

from castlib import config
from castlib.auth import cdp
from castlib.errors import AuthError

ENV = "CAST_TV_BROWSER"
PROFILE_NAME = "gopro-browser"
CACHE_NAME = "gopro-browser-cache"
PORT_FILE = "DevToolsActivePort"
LAUNCH_LOG = "cast-tv-launch.log"      # the browser's stderr, for the reason when it fails to start
START_URL = "https://gopro.com/media-library/"
COOKIE_NAME = "gp_access_token"
COOKIE_DOMAIN = "gopro.com"
HANDOFF_TIMEOUT = 300.0                 # seconds the window may stay open, like Google's consent
LAUNCH_TIMEOUT = 15.0                   # seconds a candidate has to write its DevTools port
POLL_INTERVAL = 1.0                     # seconds between Storage.getCookies calls
CLOSE_GRACE = 3.0                       # seconds after Browser.close before terminate, then kill
LINUX_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
               "microsoft-edge", "microsoft-edge-stable", "brave-browser")
WINDOWS_BROWSERS = (("chrome.exe", ("Google", "Chrome", "Application", "chrome.exe")),
                    ("msedge.exe", ("Microsoft", "Edge", "Application", "msedge.exe")))
WINDOWS_ROOTS = ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
# Read by Chrome when the profile is created; never rewritten afterwards (Chrome owns it then).
PREFERENCES = {"credentials_enable_service": False, "profile": {"password_manager_enabled": False}}

launch = subprocess.Popen       # replaced in tests by a callable returning a fake process
connect = cdp.connect           # replaced in tests


# ------------------------------------------------------------- candidates
def _app_paths(exe: str) -> list[str]:
    """The ``App Paths`` registry value for ``exe`` under HKLM, then HKCU (Windows only)."""
    try:
        import winreg
    except ImportError:
        return []
    out = []
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\App Paths\%s" % exe) as key:
                value, _ = winreg.QueryValueEx(key, None)
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            out.append(os.path.expandvars(value.strip().strip('"')))
    return out


def _windows_candidates(environ, app_paths) -> list[str]:
    found = []
    for exe, suffix in WINDOWS_BROWSERS:      # Chrome before Edge, as on the other systems
        found.extend(app_paths(exe))
        for var in WINDOWS_ROOTS:
            base = environ.get(var)
            if base:
                found.append(os.path.join(base, *suffix))
    return found


def candidates(platform=None, environ=None, which=None, isfile=os.path.isfile, app_paths=None) -> list[str]:
    """Executables to try, in order; with ``CAST_TV_BROWSER`` set, that one alone, whether or not it exists."""
    environ = os.environ if environ is None else environ
    override = (environ.get(ENV) or "").strip()
    if override:
        return [override]
    platform = platform or sys.platform
    if platform == "win32":
        found = _windows_candidates(environ, app_paths or _app_paths)
    else:
        which = which or shutil.which
        found = [which(name) for name in LINUX_NAMES]
    out: list[str] = []
    for path in found:
        if path and isfile(path) and path not in out:
            out.append(path)
    return out


def describe(environ=None) -> str:
    """For ``--version``: the override (with ``(not found)`` when missing), else the first candidate, else ``none found``."""
    environ = os.environ if environ is None else environ
    override = (environ.get(ENV) or "").strip()
    if override:
        return "%s=%s%s" % (ENV, override, "" if os.path.isfile(override) else " (not found)")
    found = candidates(environ=environ)
    return found[0] if found else "none found"


# ---------------------------------------------------------------- profile
def profile_dir() -> str:
    return os.path.join(config.config_dir(), PROFILE_NAME)


def cache_dir_for_profile() -> str:
    return os.path.join(config.cache_dir(), CACHE_NAME)


def prepare_profile() -> tuple[str, str]:
    """Create the profile (0700 on POSIX) and its cache directory; seed ``Preferences`` once. Returns both paths."""
    profile, cache = profile_dir(), cache_dir_for_profile()
    os.makedirs(profile, mode=0o700, exist_ok=True)
    if os.name == "posix":
        os.chmod(profile, 0o700)
    os.makedirs(cache, exist_ok=True)
    prefs = os.path.join(profile, "Default", "Preferences")
    if not os.path.exists(prefs):
        config.write_json(prefs, PREFERENCES)
    return profile, cache


def remove_profile() -> None:
    """Remove the profile and its cache; nothing to do when they are absent."""
    shutil.rmtree(profile_dir(), ignore_errors=True)
    shutil.rmtree(cache_dir_for_profile(), ignore_errors=True)


def flags(executable: str, profile: str, cache: str, platform=None) -> list[str]:
    """The command line: the private profile, a random DevTools port, gopro.com as an app window."""
    args = [executable, "--user-data-dir=" + profile, "--disk-cache-dir=" + cache,
            "--remote-debugging-port=0", "--no-first-run", "--no-default-browser-check"]
    if (platform or sys.platform) != "win32":
        args.append("--password-store=basic")    # a fresh profile must not pop a keyring unlock dialog
    args.append("--app=" + START_URL)
    return args


# ---------------------------------------------------------------- launch
def _read_port(path: str) -> tuple[int, str] | None:
    """``(port, /devtools/browser/<uuid>)`` from ``DevToolsActivePort``, or ``None`` while it is not there yet."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    if len(lines) < 2 or not lines[0].strip().isdigit() or not lines[1].startswith("/"):
        return None                              # half written
    return int(lines[0].strip()), lines[1].strip()


def _tail(path: str, limit: int = 400) -> str:
    """The last lines of the launch log, one string, for a failure's reason."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 4096))
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " | ".join(lines[-3:])[-limit:]


def _wait(proc, seconds: float) -> bool:
    try:
        proc.wait(timeout=seconds)
        return True
    except subprocess.TimeoutExpired:
        return False


def _end(proc, grace: float) -> None:
    """Give the process ``grace`` seconds to leave by itself, then terminate, then kill."""
    if grace > 0 and _wait(proc, grace):
        return
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except OSError:
        return
    if _wait(proc, CLOSE_GRACE):
        return
    try:
        proc.kill()
    except OSError:
        return
    _wait(proc, CLOSE_GRACE)


class Handoff:
    """One round: launch a browser on gopro.com, poll its cookies, verify, close.

    ``start(verify)`` returns at once and runs the round on a daemon thread;
    ``wait()`` blocks for its outcome: the result ``{"token", "captured_at",
    "cookie": {"session", "expires"}}``, or ``AuthError`` with the code
    ``no_browser`` (no candidate at all), ``browser_failed`` (every candidate
    failed to yield a DevTools port, or the running browser refused the
    command or lost the connection; the reason attached, no retry),
    ``browser_closed`` (the process ended before a value verified),
    ``browser_timeout`` (the deadline passed; the window was closed) or
    ``cancelled``. Only ``no_browser`` and ``browser_failed`` are failures of
    the mechanism; the source offers the token paste for those alone. ``cancel()``
    closes the browser this object launched - ``Browser.close`` first, so the
    profile's cookies are flushed, then ``terminate``, then ``kill`` - and
    never any other process.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._proc = None
        self._session: cdp.Session | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()           # set by cancel(): the poll wakes at once
        self._done = threading.Event()
        self._cancelled = False
        self.executable: str | None = None       # the candidate that yielded a port
        self.result: dict | None = None
        self.error: AuthError | None = None

    # ----------------------------------------------------------- control
    def start(self, verify, timeout: float = HANDOFF_TIMEOUT) -> Handoff:
        """Run the round on a thread; ``verify(value) -> bool`` proves a cookie value (``AuthError`` counts as ``False``)."""
        if self._thread is not None:
            raise RuntimeError("a hand-off starts once")
        self._thread = threading.Thread(target=self._run, args=(verify, timeout), name="gopro-window", daemon=True)
        self._thread.start()
        return self

    def wait(self) -> dict:
        """Block for the outcome: the result, or the round's ``AuthError``."""
        self._done.wait()
        if self.error is not None:
            raise self.error
        return self.result or {}

    def cancel(self) -> None:
        """End the round and close the window it opened; a no-op when nothing runs."""
        self._cancelled = True
        self._stop.set()
        thread = self._thread
        if thread is None or thread is threading.current_thread():
            return
        thread.join(LAUNCH_TIMEOUT + 3 * CLOSE_GRACE + cdp.CALL_TIMEOUT)
        if thread.is_alive():                    # stuck past every grace: end the process without the session
            with self._lock:
                proc = self._proc
            if proc is not None:
                _end(proc, 0)

    # ------------------------------------------------------------- the round
    def _run(self, verify, timeout: float) -> None:
        try:
            self.result = self._handoff(verify, timeout)
        except AuthError as e:
            self.error = e
        except Exception as e:                   # the thread must not die with the round still "running"
            self.error = AuthError("browser_failed", "The gopro.com window failed: %s" % e, source="gopro")
        finally:
            self._shutdown()
            self._done.set()

    def _cancelled_error(self) -> AuthError:
        return AuthError("cancelled", "The gopro.com window was cancelled.", source="gopro")

    def _handoff(self, verify, timeout: float) -> dict:
        paths = candidates()
        if not paths:
            raise AuthError("no_browser", "No Chrome, Chromium, Edge or Brave was found on this computer.",
                            source="gopro")
        profile, cache = prepare_profile()
        reasons = []
        session = None
        for path in paths:
            if self._cancelled:
                raise self._cancelled_error()
            session, reason = self._launch(path, profile, cache)
            if session is not None:
                self.executable = path
                break
            reasons.append("%s: %s" % (path, reason))
        if session is None:
            raise AuthError("browser_failed", "No gopro.com window could be opened. " + "; ".join(reasons),
                            source="gopro")
        return self._poll(session, verify, timeout)

    def _launch(self, path: str, profile: str, cache: str) -> tuple[cdp.Session | None, str | None]:
        """Launch ``path`` and connect to its DevTools port: ``(session, None)``, or ``(None, reason)``."""
        port_file = os.path.join(profile, PORT_FILE)
        try:
            os.unlink(port_file)                 # last run's port, or the wait would read it
        except OSError:
            pass
        log_path = os.path.join(profile, LAUNCH_LOG)
        try:
            with open(log_path, "wb") as log:
                proc = launch(flags(path, profile, cache), stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=log)
        except OSError as e:
            return None, str(e)
        with self._lock:
            self._proc = proc
        deadline = time.monotonic() + LAUNCH_TIMEOUT
        while True:
            if self._cancelled:
                raise self._cancelled_error()
            found = _read_port(port_file)
            if found is not None:
                break
            if proc.poll() is not None:
                self._forget(proc)
                return None, "exited with code %s (%s)" % (proc.returncode, _tail(log_path) or "no output")
            if time.monotonic() > deadline:
                self._forget(proc)
                _end(proc, 0)
                return None, "no DevTools port within %d s (%s)" % (LAUNCH_TIMEOUT, _tail(log_path) or "no output")
            time.sleep(0.05)
        port, ws_path = found
        try:
            session = connect("ws://127.0.0.1:%d%s" % (port, ws_path))
        except cdp.CdpError as e:
            self._forget(proc)
            _end(proc, 0)
            return None, "DevTools refused the connection (%s)" % e.message
        with self._lock:
            self._session = session
        return session, None

    def _forget(self, proc) -> None:
        with self._lock:
            if self._proc is proc:
                self._proc = None

    def _poll(self, session: cdp.Session, verify, timeout: float) -> dict:
        """``Storage.getCookies`` every ``POLL_INTERVAL`` until a ``gp_access_token`` value verifies."""
        deadline = time.monotonic() + timeout
        tried: set[str] = set()
        while True:
            if self._cancelled:
                raise self._cancelled_error()
            if time.monotonic() > deadline:
                raise AuthError("browser_timeout",
                                "No gopro.com session appeared within %d minutes; the window was closed."
                                % max(1, round(timeout / 60)), source="gopro")
            with self._lock:
                proc = self._proc
            if proc is not None and proc.poll() is not None:
                raise self._closed_error()
            try:
                answer = session.call("Storage.getCookies")
            except cdp.CdpError as e:
                if self._cancelled:
                    raise self._cancelled_error()
                # the window went, and the process with it (given the grace): closed by the person;
                # a browser still running that refused the command or lost the socket: the mechanism failed
                if proc is not None and (proc.poll() is not None or _wait(proc, CLOSE_GRACE)):
                    raise self._closed_error()
                raise AuthError("browser_failed", "The gopro.com window stopped answering over DevTools (%s); "
                                "it was closed." % e.message, source="gopro")
            for cookie in answer.get("cookies") or []:
                if not isinstance(cookie, dict) or cookie.get("name") != COOKIE_NAME:
                    continue
                domain = str(cookie.get("domain") or "")
                if domain != COOKIE_DOMAIN and not domain.endswith("." + COOKIE_DOMAIN):
                    continue
                value = cookie.get("value")
                if not isinstance(value, str) or not value or value in tried:
                    continue
                tried.add(value)
                try:
                    good = bool(verify(value))
                except AuthError:
                    good = False
                except Exception:
                    tried.discard(value)         # not refused, not proven: tried again on the next poll
                    good = False
                if good:
                    return {"token": value, "captured_at": time.time(),
                            "cookie": {"session": bool(cookie.get("session")), "expires": cookie.get("expires")}}
            if self._stop.wait(POLL_INTERVAL):
                raise self._cancelled_error()

    def _closed_error(self) -> AuthError:
        return AuthError("browser_closed", "The gopro.com window was closed before a session appeared.",
                         source="gopro")

    def _shutdown(self) -> None:
        """Close what this round opened: ``Browser.close`` over the session, then the process with its grace."""
        with self._lock:
            proc, session = self._proc, self._session
            self._proc = self._session = None
        if session is not None:
            try:
                session.call("Browser.close", timeout=CLOSE_GRACE)
            except cdp.CdpError:
                pass
            session.close()
        if proc is not None:
            _end(proc, CLOSE_GRACE if session is not None else 0)
