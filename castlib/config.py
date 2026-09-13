"""Where cast-tv keeps its small files, and how it writes them safely.

``config_dir()`` holds tokens and settings, ``cache_dir()`` metadata such as the
GoPro listing, never media bytes. Converted photos live in a per-process
temporary directory that disappears with the process. Paths are hard-coded to
the Linux locations until Phase 7 swaps in platformdirs.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import tempfile
import threading

from castlib.errors import ConfigError

_CONFIG = os.path.expanduser("~/.config/cast-tv")
_CACHE = os.path.expanduser("~/.cache/cast-tv")
_photo_tmp: str | None = None
# Videos fetched whole (castlib.downloads) can be gigabytes: on Fedora /tmp is RAM-backed
# (tmpfs), /var/tmp is on disk. Elsewhere (Windows) the default temp dir is on disk.
VIDEO_BASE: str | None = "/var/tmp" if os.path.isdir("/var/tmp") and os.access("/var/tmp", os.W_OK) else None
_video_tmp: str | None = None
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
    """The per-process directory for videos fetched whole; created on first use, removed at exit."""
    global _video_tmp
    with _photo_lock:
        if _video_tmp is None or not os.path.isdir(_video_tmp):
            _video_tmp = tempfile.mkdtemp(prefix="cast-tv-videos-", dir=VIDEO_BASE)
            atexit.register(remove_video_tmp_dir)
        return _video_tmp


def remove_video_tmp_dir() -> None:
    """Delete the video directory now."""
    global _video_tmp
    with _photo_lock:
        path, _video_tmp = _video_tmp, None
    if path:
        shutil.rmtree(path, ignore_errors=True)
