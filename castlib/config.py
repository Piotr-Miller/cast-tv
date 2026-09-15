"""Where cast-tv keeps its small files, and how it writes them safely.

``config_dir()`` holds tokens and settings, ``cache_dir()`` metadata such as the
GoPro listing, never media bytes. Converted photos live in a per-process
temporary directory that disappears with the process. ``platformdirs`` places
them: ``~/.config/cast-tv`` and ``~/.cache/cast-tv`` on Linux (the paths used
before it arrived, so nothing moves), ``%APPDATA%\\cast-tv`` and
``%LOCALAPPDATA%\\cast-tv\\Cache`` on Windows.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import stat
import sys
import tempfile
import threading

from castlib.errors import ConfigError

APP_DIR = "cast-tv"


def platform_dirs(platform: str | None = None) -> tuple[str, str]:
    """``(config, cache)`` directories for ``platform`` (default: this one).

    ``appauthor=False`` keeps Windows from nesting the name twice
    (``cast-tv\\cast-tv``); ``roaming=True`` puts the config under ``%APPDATA%``,
    where Windows keeps per-user settings, and changes nothing elsewhere.
    """
    platform = platform or sys.platform
    if platform == "win32":
        from platformdirs.windows import Windows as Dirs
    elif platform == "darwin":
        from platformdirs.macos import MacOS as Dirs
    else:
        from platformdirs.unix import Unix as Dirs
    dirs = Dirs(APP_DIR, appauthor=False, roaming=True)
    return dirs.user_config_dir, dirs.user_cache_dir


_CONFIG, _CACHE = platform_dirs()
_photo_tmp: str | None = None
# Videos fetched whole (castlib.downloads) can be gigabytes: on Fedora /tmp is RAM-backed
# (tmpfs), /var/tmp is on disk. Elsewhere (Windows) the default temp dir is on disk.
VIDEO_BASE: str | None = "/var/tmp" if os.path.isdir("/var/tmp") and os.access("/var/tmp", os.W_OK) else None
_video_tmp: str | None = None
VIDEO_PREFIX = "cast-tv-videos-"      # then "<pid>-": what a startup sweep can prove orphaned
_photo_lock = threading.Lock()


def config_dir() -> str:
    return _CONFIG


def cache_dir() -> str:
    return _CACHE


def _bare(name: str) -> str:
    """A cache entry is named by a bare filename; anything else is refused."""
    if (not name or name in (".", "..") or os.path.basename(name) != name
            or "/" in name or "\\" in name or "\x00" in name):
        raise ConfigError("bad_cache_name", "Not a valid cache entry name: %r" % (name,))
    return name


def write_json(path: str, data) -> None:
    """Write JSON to ``path`` atomically: a temp file in the same directory, then rename.

    The file at ``path`` is untouched until the rename; on any failure the
    temp file is removed and the exception propagates. Every JSON file
    cast-tv keeps (settings, cache entries) is written through here.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def cache_write(name: str, data) -> None:
    """Write a JSON cache entry atomically (see ``write_json``)."""
    _bare(name)
    write_json(os.path.join(_CACHE, name), data)


def cache_read(name: str):
    _bare(name)
    try:
        with open(os.path.join(_CACHE, name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_private(path: str, text: str) -> None:
    """Create or overwrite ``path`` readable by this user only (mode 0600), atomically.

    Like ``write_json``: a 0600 temp file in the same directory, then a rename,
    so a crash or a full disk mid-write never leaves a truncated credential
    behind (``TokenStore`` reads a partial file as "not signed in").
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=directory)   # mkstemp creates it 0600
    try:
        if hasattr(os, "fchmod"):            # POSIX; on Windows the per-user profile directory guards it
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def photo_tmp_dir() -> str:
    """The per-process directory for converted photos; created on first use, removed at exit."""
    global _photo_tmp
    with _photo_lock:
        if _photo_tmp is None or not os.path.isdir(_photo_tmp):
            _photo_tmp = tempfile.mkdtemp(prefix="cast-tv-photos-")
            atexit.register(remove_photo_tmp_dir)
        return _photo_tmp


def remove_photo_tmp_dir() -> None:
    """Delete the photo directory now (also called from Ctrl+C handlers)."""
    global _photo_tmp
    with _photo_lock:
        path, _photo_tmp = _photo_tmp, None
    if path:
        shutil.rmtree(path, ignore_errors=True)


def video_tmp_dir() -> str:
    """The per-process directory for videos fetched whole; created on first use, removed at exit.

    Its name carries the process id, so a run killed before its ``atexit``
    leaves a directory ``sweep_stale_video_dirs`` can recognise.
    """
    global _video_tmp
    with _photo_lock:
        if _video_tmp is None or not os.path.isdir(_video_tmp):
            _video_tmp = tempfile.mkdtemp(prefix="%s%d-" % (VIDEO_PREFIX, os.getpid()), dir=VIDEO_BASE)
            atexit.register(remove_video_tmp_dir)
        return _video_tmp


def remove_video_tmp_dir() -> None:
    """Delete the video directory now."""
    global _video_tmp
    with _photo_lock:
        path, _video_tmp = _video_tmp, None
    if path:
        shutil.rmtree(path, ignore_errors=True)


def sweep_stale_video_dirs() -> list[str]:
    """Remove the video directories of cast-tv processes that died without cleaning up.

    Only ``cast-tv-videos-<pid>-*`` directories (not symlinks) owned by this
    user, whose process no longer exists, are removed; a name without a pid (an
    older release's) or an owner that may be alive keeps its directory. On
    Windows the directory sits in the per-user ``%TEMP%``, so ownership is not
    checked, and liveness is asked of ``OpenProcess`` rather than ``os.kill``
    (which would terminate the process there). Returns the removed paths.
    """
    base = VIDEO_BASE or tempfile.gettempdir()
    try:
        names = os.listdir(base)
    except OSError:
        return []
    removed = []
    for name in names:
        pid_text, sep, _ = name[len(VIDEO_PREFIX):].partition("-")
        if not name.startswith(VIDEO_PREFIX) or not sep or not (pid_text.isascii() and pid_text.isdigit()):
            continue
        pid = int(pid_text)
        path = os.path.join(base, name)
        try:
            st = os.lstat(path)
        except OSError:
            continue
        if (pid == os.getpid() or not stat.S_ISDIR(st.st_mode)
                or (hasattr(os, "getuid") and st.st_uid != os.getuid()) or _alive(pid)):
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path)
    return removed


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        return _alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:                          # EPERM: a live process of someone else
        return True
    return True


def _alive_windows(pid: int, kernel32=None, last_error=None) -> bool:
    """Whether ``pid`` names a running process, asked without touching it.

    ``OpenProcess`` fails with ERROR_INVALID_PARAMETER for a pid no process
    holds; any other failure (access denied: someone else's process) counts as
    alive, and so does an open handle whose exit code is still STILL_ACTIVE.
    """
    import ctypes
    from ctypes import wintypes
    if kernel32 is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE      # the default int would truncate a 64-bit handle
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE, ERROR_INVALID_PARAMETER = 0x1000, 259, 87
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return (last_error or ctypes.get_last_error)() != ERROR_INVALID_PARAMETER
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)
