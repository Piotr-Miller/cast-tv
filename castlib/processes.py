"""Running processes and the executables they run from: what ``startup_time.py`` and the cache pruning check.

``running_images()`` lists (pid, image path) for every process this user can see. A
process that ends during the scan is skipped. A process that is ours but cannot be read
makes the listing incomplete (``IncompleteListing``): whoever decides from it must not
assume that nothing uses a file. Another user's process that refuses is skipped: it
cannot be running from this user's cache. "Ours" is the same owner on Linux
(``/proc/<pid>`` belongs to us) and the same logon session on Windows, where no process of
the user's own session refused the image-path query on the home machine (2026-11-18).
"""
import os
import sys


class IncompleteListing(Exception):
    """A process of this user could not be read; the list may miss a running copy."""


def running_images(platform=None, proc_root="/proc", win=None) -> list[tuple[int, str]]:
    platform = platform or sys.platform
    if platform == "win32":
        return _windows(win or _Win32())
    if platform.startswith("linux"):
        return _linux(proc_root)
    raise IncompleteListing("processes cannot be listed on %s" % platform)


# ------------------------------------------------------------------ Linux
def _linux(root: str) -> list[tuple[int, str]]:
    try:
        names = os.listdir(root)
    except OSError as e:
        raise IncompleteListing("cannot read %s: %s" % (root, e))
    me = os.getuid() if hasattr(os, "getuid") else None
    found = []
    for name in names:
        if not name.isdigit():
            continue
        path = os.path.join(root, name)
        try:
            found.append((int(name), os.readlink(os.path.join(path, "exe"))))
        except (FileNotFoundError, ProcessLookupError):
            continue                                   # gone, or a kernel thread with no executable
        except PermissionError:
            try:
                owner = os.stat(path).st_uid
            except FileNotFoundError:
                continue                               # it ended meanwhile
            except OSError as e:
                raise IncompleteListing("cannot read process %s: %s" % (name, e))
            if owner == me:
                raise IncompleteListing("process %s is ours but its executable cannot be read" % name)
        except OSError as e:
            raise IncompleteListing("cannot read process %s: %s" % (name, e))
    return found


# ---------------------------------------------------------------- Windows
class Gone(Exception):
    """The process ended before it could be read."""


class Denied(Exception):
    """The process refused the query."""


class _Win32:
    """The few Win32 calls the listing needs, through ctypes."""

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    ERROR_INVALID_PARAMETER = 87              # OpenProcess's answer for a pid that no longer exists

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.w = ctypes, wintypes
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self.k32.OpenProcess.restype = wintypes.HANDLE
        self.k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        self.k32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                        ctypes.POINTER(wintypes.DWORD))
        self.k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.k32.ProcessIdToSessionId.argtypes = (wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))

    def pids(self) -> list[int]:
        size = 1024
        while True:
            arr = (self.w.DWORD * size)()
            needed = self.w.DWORD()
            if not self.psapi.EnumProcesses(arr, self.ctypes.sizeof(arr), self.ctypes.byref(needed)):
                raise IncompleteListing("EnumProcesses failed (%d)" % self.ctypes.get_last_error())
            if needed.value < self.ctypes.sizeof(arr):
                return [p for p in arr[: needed.value // 4] if p]
            size *= 2

    def session(self, pid: int) -> int | None:
        s = self.w.DWORD()
        return s.value if self.k32.ProcessIdToSessionId(pid, self.ctypes.byref(s)) else None

    def image(self, pid: int) -> str:
        h = self.k32.OpenProcess(self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            err = self.ctypes.get_last_error()
            raise Gone() if err == self.ERROR_INVALID_PARAMETER else Denied(err)
        try:
            buf = self.ctypes.create_unicode_buffer(32768)
            size = self.w.DWORD(32768)
            if not self.k32.QueryFullProcessImageNameW(h, 0, buf, self.ctypes.byref(size)):
                raise Denied(self.ctypes.get_last_error())
            return buf.value
        finally:
            self.k32.CloseHandle(h)


def _windows(api) -> list[tuple[int, str]]:
    mine = api.session(os.getpid())
    if mine is None:
        raise IncompleteListing("this process's session is unknown")
    found = []
    for pid in api.pids():
        try:
            found.append((pid, api.image(pid)))
        except Gone:
            continue
        except Denied as e:
            session = api.session(pid)
            if session is None:
                continue                               # ended between the two calls
            if session == mine:
                raise IncompleteListing("process %d in this session refused its image path (%s)" % (pid, e))
    return found
