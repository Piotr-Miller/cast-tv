"""What differs per operating system: firewall advice and staying awake.

``StayAwake`` is counted: the supervisor holds it once per promoted cast and
once per running show, and the machine is kept awake while the count is above
zero. The backend is ``systemd-inhibit`` on Linux and
``SetThreadExecutionState`` on Windows; anywhere else, or when the backend
fails, staying awake is best effort and never stops a cast.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading


def firewall_hint(port: int) -> str:
    """The one command that opens the media port on this platform."""
    if sys.platform == "win32":
        return ('netsh advfirewall firewall add rule name="cast-tv" dir=in action=allow '
                "protocol=TCP localport=%d" % port)
    return "sudo firewall-cmd --add-port=%d/tcp" % port


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
