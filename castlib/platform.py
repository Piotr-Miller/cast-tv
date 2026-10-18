"""What differs per operating system: firewall advice, staying awake, a closed console, the session's end.

``StayAwake`` is counted: the supervisor holds it once per promoted cast and
once per running show, and the machine is kept awake while the count is above
zero. The backend is ``systemd-inhibit`` on Linux and
``SetThreadExecutionState`` on Windows; anywhere else, or when the backend
fails, staying awake is best effort and never stops a cast.

``end_on_console_close`` makes closing the console window on Windows end
cast-tv the way Ctrl+C does, instead of the process simply being ended;
``end_on_session_end`` does the same for logging off and shutting down while
the cast-tv window is open.

``use_system_ca_bundle`` points the Linux release binary at this machine's
CA certificates: it carries the OpenSSL of the distribution it was built on,
which looks for them where that distribution keeps them.
"""
from __future__ import annotations

import _thread
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
from types import SimpleNamespace


def firewall_hint(port: int) -> str:
    """The one command that opens the media port on this platform."""
    if sys.platform == "win32":
        return ('netsh advfirewall firewall add rule name="cast-tv" dir=in action=allow '
                "protocol=TCP localport=%d" % port)
    return "sudo firewall-cmd --add-port=%d/tcp" % port


# An inbound Block rule on every port, program and address - what an organisation's MDM pushes to
# a managed laptop - outranks any allow rule, so the command above cannot help. Reading the active
# store needs no administrator rights.
FIREWALL_QUERY = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$profiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue | ForEach-Object { [string]$_.NetworkCategory })
$rules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Direction Inbound -Action Block -Enabled True -ErrorAction SilentlyContinue |
  Where-Object {
    $port = $_ | Get-NetFirewallPortFilter
    $app = $_ | Get-NetFirewallApplicationFilter
    $addr = $_ | Get-NetFirewallAddressFilter
    ($port.Protocol -in 'Any', 'TCP') -and ($port.LocalPort -contains 'Any') -and
      ($app.Program -eq 'Any') -and ($addr.RemoteAddress -contains 'Any')
  } | ForEach-Object { @{ name = [string]$_.DisplayName; profile = [string]$_.Profile } })
@{ profiles = $profiles; rules = $rules } | ConvertTo-Json -Compress -Depth 3
"""
_CATEGORY = {"Public": "Public", "Private": "Private", "DomainAuthenticated": "Domain"}


def blocking_rule(report: dict) -> str | None:
    """The name of a block-all rule that applies to a network this machine is on, from ``FIREWALL_QUERY``."""
    profiles = {_CATEGORY.get(p, p) for p in report.get("profiles") or []}
    for rule in report.get("rules") or []:
        applies = {part.strip() for part in str(rule.get("profile") or "").split(",")}
        if "Any" in applies or applies & profiles:
            return str(rule.get("name") or "an inbound block rule")
    return None


class FirewallPolicy:
    """Whether Windows' firewall policy blocks every inbound connection; asked once, in the background.

    ``blocked()`` is the rule's name or None; None as well when the question
    could not be answered (no PowerShell, a timeout, anything unexpected), so
    the advice falls back to the ``netsh`` command.
    """

    TIMEOUT = 15

    def __init__(self, run=subprocess.run, platform=None):
        self._run = run
        self._platform = platform or sys.platform
        self._done = threading.Event()
        self._started = False
        self._lock = threading.Lock()
        self._rule: str | None = None

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        if self._platform != "win32":
            self._done.set()
            return
        threading.Thread(target=self._ask, name="firewall-policy", daemon=True).start()

    def _ask(self) -> None:
        try:
            import json
            proc = self._run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", FIREWALL_QUERY],
                             capture_output=True, timeout=self.TIMEOUT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            text = proc.stdout.decode("utf-8", "replace").strip() if proc.stdout else ""
            self._rule = blocking_rule(json.loads(text)) if text else None
        except Exception:
            self._rule = None
        finally:
            self._done.set()

    def blocked(self, wait: float = 0) -> str | None:
        """The blocking rule's name, or None; waits up to ``wait`` seconds for the answer."""
        self.start()
        self._done.wait(wait)
        return self._rule


firewall_policy = FirewallPolicy()


def firewall_blocked(wait: float = 0) -> str | None:
    """``firewall_policy.blocked()``, looked up at call time so the test suite can swap the policy."""
    return firewall_policy.blocked(wait)


def firewall_advice(port: int, wait: float = 0) -> str:
    """What to do when the TV fetches nothing: open the port, or why that cannot work here."""
    rule = firewall_blocked(wait)
    if rule:
        return ("This computer's firewall policy blocks every incoming connection (the rule \"%s\", "
                "usually set by your organisation), and no allow rule can override it, so the TV "
                "cannot fetch from this computer. Cast from another computer, or ask your IT "
                "department to allow incoming TCP port %d." % (rule, port))
    if sys.platform == "win32":
        return "Open the port, in PowerShell as administrator:  " + firewall_hint(port)
    return "Open the port:  " + firewall_hint(port)


class NullBackend:
    """Nothing to hold: platforms without a known mechanism, and the test suite."""

    def acquire(self) -> None:
        pass

    def release(self) -> None:
        pass


class SystemdInhibit:
    """A ``systemd-inhibit`` child holding an idle and sleep lock until it is killed.

    The child blocks on ``cat`` reading a pipe from this process rather than on
    ``sleep infinity``: if cast-tv dies without releasing (SIGKILL, a crash),
    the pipe closes, ``cat`` exits and logind drops the lock with it.
    """

    COMMAND = ["systemd-inhibit", "--what=idle:sleep", "--who=cast-tv",
               "--why=casting to the TV", "--mode=block", "cat"]

    def __init__(self, which=shutil.which, popen=subprocess.Popen):
        self._which = which
        self._popen = popen
        self._proc = None

    def acquire(self) -> None:
        if self._proc is not None or not self._which("systemd-inhibit"):
            return
        self._proc = self._popen(self.COMMAND, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def release(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()          # EOF: cat exits, the inhibitor goes with it
            proc.wait(timeout=2)
        except Exception:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except Exception:
                pass


class ExecutionState:
    """``SetThreadExecutionState`` from a thread that lives as long as the hold.

    The flags apply to the calling thread and lapse when it ends, so one
    dedicated thread sets them, waits for ``release()`` and resets them to
    ``ES_CONTINUOUS`` before it exits.
    """

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002

    def __init__(self, kernel32=None):
        self._kernel32 = kernel32
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def _k32(self):
        if self._kernel32 is None:
            import ctypes
            self._kernel32 = ctypes.WinDLL("kernel32")
            self._kernel32.SetThreadExecutionState.restype = ctypes.c_uint32
            self._kernel32.SetThreadExecutionState.argtypes = (ctypes.c_uint32,)
        return self._kernel32

    def acquire(self) -> None:
        if self._thread is not None:
            return
        k32 = self._k32()
        stop = threading.Event()
        held = threading.Event()

        def hold():
            try:
                k32.SetThreadExecutionState(self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED
                                            | self.ES_DISPLAY_REQUIRED)
                held.set()
                stop.wait()
            finally:
                held.set()
                k32.SetThreadExecutionState(self.ES_CONTINUOUS)

        self._stop = stop
        self._thread = threading.Thread(target=hold, name="stay-awake", daemon=True)
        self._thread.start()
        held.wait(2)

    def release(self) -> None:
        thread, stop = self._thread, self._stop
        self._thread = self._stop = None
        if thread is None:
            return
        stop.set()
        thread.join(2)


def default_backend():
    if sys.platform == "win32":
        return ExecutionState()
    if sys.platform.startswith("linux"):
        return SystemdInhibit()
    return NullBackend()


class StayAwake:
    """Keeps the machine from sleeping while something plays; counted, so nested use is safe.

    The backend is taken on the first ``start()`` and let go on the ``stop()``
    that brings the count back to zero; its failures are swallowed.
    """

    def __init__(self, backend=None):
        self._count = 0
        self._lock = threading.Lock()
        self._backend = backend if backend is not None else default_backend()

    def start(self) -> None:
        with self._lock:
            self._count += 1
            if self._count == 1:
                try:
                    self._backend.acquire()
                except Exception:
                    pass

    def stop(self) -> None:
        with self._lock:
            if self._count > 0:
                self._count -= 1
                if self._count == 0:
                    try:
                        self._backend.release()
                    except Exception:
                        pass

    def close(self) -> None:
        """Let go whatever the count says: the process is ending."""
        with self._lock:
            held, self._count = self._count, 0
            if held:
                try:
                    self._backend.release()
                except Exception:
                    pass

    @property
    def active(self) -> bool:
        with self._lock:
            return self._count > 0


class ConsoleClose:
    """Windows: closing the console window, logging off or shutting down ends cast-tv like Ctrl+C.

    Windows delivers these as ``CTRL_CLOSE_EVENT``, ``CTRL_LOGOFF_EVENT`` and
    ``CTRL_SHUTDOWN_EVENT``, which Python does not turn into
    ``KeyboardInterrupt``: without a handler the process is ended outright - no
    ``Stop`` to the TV, which shows a broken-stream error mid-film or keeps a
    photo up, no ``close()`` on the sources, no ``atexit``. The handler runs on
    a thread of its own: it interrupts the main thread, whose
    ``except KeyboardInterrupt`` already stops the TV and cleans up, and then
    waits. The process is ended as soon as the handler returns, so it waits out
    the grace Windows gives (about 5 s) unless the main thread exits first,
    which ends the process with the handler still waiting. Measured behind the
    pipx launcher and the venv's ``python.exe``: both let the Python process
    run out its handler before they go.

    In window mode the main thread sits in the GUI loop, where an interrupt
    would only break ``webview.start()`` and leave the window up: ``on_end``
    (the window's ``destroy``) is called instead, and the main thread stops
    the TV once the GUI loop returns. WinForms loads user32, after which
    Windows no longer sends the logoff and shutdown events here; ``SessionEnd``
    takes those over.
    """

    CLOSE_EVENTS = (2, 5, 6)        # CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT
    GRACE = 4.5                     # seconds; Windows ends the process at about 5

    def __init__(self, kernel32=None, interrupt=_thread.interrupt_main, sleep=time.sleep, on_end=None):
        self._kernel32 = kernel32
        self._interrupt = interrupt
        self._sleep = sleep
        self.on_end = on_end        # None: interrupt the main thread, as Ctrl+C would
        self._callback = None       # the ctypes callback must outlive the registration

    def handle(self, event: int) -> bool:
        """True when the event is ours; Ctrl+C and Ctrl+Break go on to Python's own handler."""
        if event not in self.CLOSE_EVENTS:
            return False
        (self.on_end or self._interrupt)()
        self._sleep(self.GRACE)
        return True

    def install(self) -> bool:
        import ctypes
        from ctypes import wintypes
        k32 = self._kernel32
        if k32 is None:
            k32 = ctypes.WinDLL("kernel32")
            k32.SetConsoleCtrlHandler.restype = wintypes.BOOL
        routine = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
        self._callback = routine(lambda event: bool(self.handle(event)))
        return bool(k32.SetConsoleCtrlHandler(self._callback, True))


_console_close: ConsoleClose | None = None


def end_on_console_close() -> bool:
    """Install ``ConsoleClose`` once, on Windows; elsewhere a closed terminal already sends SIGHUP."""
    global _console_close
    if sys.platform != "win32" or _console_close is not None:
        return False
    handler = ConsoleClose()
    try:
        if not handler.install():
            return False
    except Exception:
        return False
    _console_close = handler
    return True


def console_close_ends(on_end) -> None:
    """What a closed console does from now on: ``on_end()``, or Ctrl+C's interrupt again for None."""
    if _console_close is not None:
        _console_close.on_end = on_end


class SessionEnd:
    """Windows, window mode: logging off or shutting down ends cast-tv like closing its window.

    Once WinForms has loaded user32, ``SetConsoleCtrlHandler`` no longer
    receives ``CTRL_LOGOFF_EVENT`` or ``CTRL_SHUTDOWN_EVENT``; Windows sends
    ``WM_QUERYENDSESSION`` and ``WM_ENDSESSION`` to every top-level window
    instead (https://learn.microsoft.com/en-us/windows/console/registering-a-control-handler-function).
    The native side owns a hidden top-level window - a message-only one gets
    no broadcast - and its message loop, on a thread of its own.

    The query is answered yes and nothing is cleaned up yet: the session end
    may still be cancelled. ``WM_ENDSESSION`` with a true ``wParam`` runs
    ``on_end(absolute_deadline)`` on a worker, once, and waits for it at most ``deadline`` seconds
    counted from the first such message: Windows ends the process soon after
    the message is answered, and a TV that does not answer must not hold up
    the sign-out. A false ``wParam`` means the end was cancelled; cast-tv goes on.
    """

    WM_QUERYENDSESSION = 0x0011
    WM_ENDSESSION = 0x0016
    DEADLINE = 4.0                  # seconds, Stop and cleanup included; under the ~5 s Windows allows

    def __init__(self, on_end, native=None, deadline=DEADLINE, clock=time.monotonic,
                 wait=lambda event, timeout: event.wait(timeout)):
        self._on_end = on_end
        self._native = native
        self.deadline = deadline
        self._clock = clock
        self._wait = wait
        self._lock = threading.Lock()
        self._done: threading.Event | None = None
        self._started_at = 0.0
        self._callback = None       # the window procedure must outlive the registration

    def handle(self, msg: int, wparam: int) -> int | None:
        """The window procedure's answer to ``msg``, or None for ``DefWindowProcW``."""
        if msg == self.WM_QUERYENDSESSION:
            return 1
        if msg == self.WM_ENDSESSION:
            if wparam:
                self.end()
            return 0
        return None

    def end(self) -> bool:
        """Run ``on_end`` once and wait for it within the deadline; True when it finished in time."""
        with self._lock:
            if self._done is None:
                self._done = threading.Event()
                self._started_at = self._clock()
                threading.Thread(target=self._run, args=(self._done,), name="session-end",
                                 daemon=True).start()
            done, started = self._done, self._started_at
        left = self.deadline - (self._clock() - started)
        if left <= 0:
            return done.is_set()
        return bool(self._wait(done, left))

    def _run(self, done: threading.Event) -> None:
        try:
            self._on_end(self._started_at + self.deadline)
        except Exception:
            pass
        finally:
            done.set()

    def install(self) -> bool:
        native = self._native
        if native is None:
            native = self._native = Win32SessionWindow()
        self._callback = native.window_procedure(self.handle)
        if native.start(self._callback):
            return True
        self._callback = None
        return False

    def release(self) -> None:
        if self._native is not None and self._callback is not None:
            try:
                self._native.stop()
            finally:
                self._callback = None


class Win32SessionWindow:
    """``SessionEnd``'s native side: a hidden top-level window and its message loop, through ctypes."""

    WM_DESTROY = 0x0002
    WM_CLOSE = 0x0010

    def __init__(self):
        self._hwnd = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._api = None

    def _user32(self):
        if self._api is not None:
            return self._api
        import ctypes
        from ctypes import wintypes
        lresult = ctypes.c_ssize_t
        wndproc = ctypes.WINFUNCTYPE(lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", wndproc),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                        ("hIconSm", wintypes.HICON)]

        u32 = ctypes.WinDLL("user32", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetModuleHandleW.restype = wintypes.HMODULE
        k32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        u32.DefWindowProcW.restype = lresult
        u32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        u32.RegisterClassExW.restype = wintypes.ATOM
        u32.RegisterClassExW.argtypes = (ctypes.POINTER(WNDCLASSEXW),)
        u32.UnregisterClassW.argtypes = (wintypes.LPCWSTR, wintypes.HINSTANCE)
        u32.CreateWindowExW.restype = wintypes.HWND
        u32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
        u32.GetMessageW.restype = wintypes.BOOL
        u32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
        u32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
        u32.DispatchMessageW.restype = lresult
        u32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
        u32.PostMessageW.restype = wintypes.BOOL
        u32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        u32.PostQuitMessage.argtypes = (ctypes.c_int,)
        self._api = SimpleNamespace(ctypes=ctypes, wintypes=wintypes, u32=u32, k32=k32,
                                    WNDPROC=wndproc, WNDCLASSEXW=WNDCLASSEXW)
        return self._api

    def window_procedure(self, handle):
        """A ctypes ``WNDPROC`` that asks ``handle(msg, wparam)`` and lets ``DefWindowProcW`` answer the rest."""
        api = self._user32()

        def procedure(hwnd, msg, wparam, lparam):
            if msg == self.WM_DESTROY:
                api.u32.PostQuitMessage(0)
                return 0
            try:
                answer = handle(msg, wparam)
            except Exception:
                answer = None
            if answer is None:
                return api.u32.DefWindowProcW(hwnd, msg, wparam, lparam)
            return answer

        return api.WNDPROC(procedure)

    def start(self, procedure) -> bool:
        """Create the window and run its loop on a thread of its own; False when the window could not be made."""
        self._thread = threading.Thread(target=self._loop, args=(procedure,), name="session-end-window",
                                        daemon=True)
        self._thread.start()
        self._ready.wait(5)
        return self._hwnd is not None

    def _loop(self, procedure) -> None:
        api = self._user32()
        name = "cast-tv-session-%d" % os.getpid()
        instance = api.k32.GetModuleHandleW(None)
        try:
            wc = api.WNDCLASSEXW()
            wc.cbSize = api.ctypes.sizeof(api.WNDCLASSEXW)
            wc.lpfnWndProc = procedure
            wc.hInstance = instance
            wc.lpszClassName = name
            if not api.u32.RegisterClassExW(api.ctypes.byref(wc)):
                return
            # no WS_VISIBLE: never shown, but top-level, so the session messages reach it
            self._hwnd = api.u32.CreateWindowExW(0, name, "cast-tv", 0, 0, 0, 0, 0,
                                                 None, None, instance, None) or None
            if self._hwnd is None:
                api.u32.UnregisterClassW(name, instance)
                return
        finally:
            self._ready.set()
        msg = api.wintypes.MSG()
        while api.u32.GetMessageW(api.ctypes.byref(msg), None, 0, 0) > 0:
            api.u32.TranslateMessage(api.ctypes.byref(msg))
            api.u32.DispatchMessageW(api.ctypes.byref(msg))
        api.u32.UnregisterClassW(name, instance)

    def stop(self) -> None:
        hwnd, thread = self._hwnd, self._thread
        self._hwnd = None
        if hwnd is not None:
            self._user32().u32.PostMessageW(hwnd, self.WM_CLOSE, 0, 0)   # DefWindowProc destroys; WM_DESTROY quits the loop
        if thread is not None:
            thread.join(2)


def end_on_session_end(on_end) -> SessionEnd | None:
    """Windows: call on_end(absolute monotonic deadline) at session end. Caller releases the hook; None elsewhere."""
    if sys.platform != "win32":
        return None
    hook = SessionEnd(on_end)
    try:
        if hook.install():
            return hook
    except Exception:
        pass
    return None


# Where Linux distributions keep the CA bundle. Debian, Ubuntu and Arch come first; Fedora 44
# has the same file, a link into /etc/pki/ca-trust, and dropped the ca-bundle.crt that Fedora 42
# and RHEL still use. The last two are Alpine's and openSUSE's.
CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
    "/etc/ssl/cert.pem",
    "/etc/ssl/ca-bundle.pem",
)


def use_system_ca_bundle(environ=None, exists=os.path.exists) -> str | None:
    """Set ``SSL_CERT_FILE`` to this machine's CA bundle in the Linux release binary; the file chosen, or None.

    The binary is built on Ubuntu and carries its OpenSSL, which looks under ``/usr/lib/ssl``;
    Fedora has no such directory, so every HTTPS request failed with CERTIFICATE_VERIFY_FAILED.
    Nothing changes when the user already set ``SSL_CERT_FILE`` or ``SSL_CERT_DIR``, outside
    the frozen Linux build, or when OpenSSL's own default path exists.
    """
    environ = os.environ if environ is None else environ
    if not sys.platform.startswith("linux") or not getattr(sys, "frozen", False):
        return None
    if environ.get("SSL_CERT_FILE") or environ.get("SSL_CERT_DIR"):
        return None
    paths = ssl.get_default_verify_paths()
    if exists(paths.openssl_cafile) or exists(paths.openssl_capath):
        return None
    for bundle in CA_BUNDLES:
        if exists(bundle):
            environ["SSL_CERT_FILE"] = bundle
            return bundle
    return None
