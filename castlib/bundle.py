"""The packaged release: which packager built it, which file the user started, where its files are.

The one place that knows PyInstaller from Nuitka. A PyInstaller onefile sets
``sys.frozen`` and ``sys._MEIPASS`` (the folder it unpacked into for this run);
``sys.executable`` is the file the user started. A Nuitka onefile sets neither:
its main module carries ``__compiled__``, ``sys.executable`` is the unpacked
copy in the cache folder, and the file the user started is
``__compiled__.original_argv0``.

That value is ``argv[0]`` as the outer file received it on Linux, so a start
through PATH gives a bare name (``cast-tv-linux-x64``), and a relative one is
relative to the working directory at start. Both are captured at import,
before anything changes them. On Windows the bootstrap hands its child its
own absolute path (Nuitka 4.3.5, ``OnefileBootstrap.c:899`` and
``MainProgram.c:1930-1932``).

A Nuitka onefile release unpacks once into ``<cache root>/cast-tv/<build identity>`` and
reuses that folder on later starts (s16-faster-start). The build identity is
``<version>-gh<run id>.<run attempt>`` for a CI build or ``<version>-local<UTC
yyyymmddHHMMSS>`` for a local one: one grammar shared by the builder
(``packaging/build_nuitka.py``), the pruning of old folders and
``packaging/startup_time.py``. Nothing else under ``cast-tv`` (the GoPro browser's
``Cache`` folder on Windows) ever matches it.

Old build folders are pruned at start (``prune_caches``): the current folder and the previous
one stay, and any other stays while it was started within the last 7 days or a running process's
executable lies inside it. A start touches ``.cast-tv-started`` in its folder, the marker the
age and the "previous" pick read. A removable folder is first renamed to
``<name>.removing-<pid>`` (on Windows that fails while a file inside is locked, and the folder
stays), and only that copy is deleted.

Every function takes its inputs as parameters, so tests can stand in for
either packager. The default started file is resolved once at import;
other defaults read the running process at call time.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import time

from castlib.processes import IncompleteListing, running_images

PYINSTALLER = "pyinstaller"
NUITKA = "nuitka"

# Captured once, at import: ``started_file()`` resolves a relative or bare argv[0] against them.
_START_CWD = os.getcwd()
_START_PATH = os.environ.get("PATH", os.defpath)

# What a Nuitka onefile child inherits from its bootstrap (Nuitka 4.3.5,
# ``OnefileBootstrap.c:1124-1131,1388-1390``). A file started with them would
# take the role of a child of this run instead of a new start.
NUITKA_ONEFILE_PREFIX = "NUITKA_ONEFILE_"
NUITKA_ORIGINAL_ARGV0 = "NUITKA_ORIGINAL_ARGV0"
PYINSTALLER_RESET = "PYINSTALLER_RESET_ENVIRONMENT"

APP_DIR = "cast-tv"
BUILD_ID = re.compile(r"^\d+\.\d+\.\d+-(gh\d+\.\d+|local\d{14})$")
START_MARKER = ".cast-tv-started"
REMOVING = re.compile(r"^(\d+\.\d+\.\d+-(gh\d+\.\d+|local\d{14}))\.removing-\d+$")


def cache_root(platform=None, environ=None, home=None) -> str:
    """Nuitka's ``{CACHE_DIR}``: %LOCALAPPDATA% on Windows; $XDG_CACHE_HOME when absolute, else ~/.cache."""
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    home = home or os.path.expanduser("~")
    if platform == "win32":
        return environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    xdg = environ.get("XDG_CACHE_HOME", "")
    return xdg if os.path.isabs(xdg) else os.path.join(home, ".cache")


def cache_parent(**kw) -> str:
    """The folder that holds every build's unpacked files."""
    return os.path.join(cache_root(**kw), APP_DIR)


def is_build_folder(path: str, **kw) -> bool:
    """``path`` is a build folder directly under ``cache_parent()`` with a valid identity, nothing else."""
    parent = os.path.normcase(os.path.abspath(cache_parent(**kw)))
    full = os.path.abspath(path)
    return (os.path.normcase(os.path.dirname(full)) == parent
            and bool(BUILD_ID.match(os.path.basename(full))))


def _compiled(sys_module=None, main=None):
    """The main module's ``__compiled__`` when it is a Nuitka onefile, else None."""
    if main is None:
        modules = getattr(sys if sys_module is None else sys_module, "modules", None) or {}
        main = modules.get("__main__")
    compiled = getattr(main, "__compiled__", None)
    return compiled if compiled is not None and getattr(compiled, "onefile", False) else None


def kind(sys_module=None, main=None) -> str | None:
    """``"pyinstaller"``, ``"nuitka"`` or None (a checkout or a pip/pipx install)."""
    if _compiled(sys_module, main) is not None:
        return NUITKA
    if getattr(sys if sys_module is None else sys_module, "frozen", False):
        return PYINSTALLER
    return None


def resolve_kind(kind_: str | None = None, frozen: bool | None = None) -> str | None:
    """The kind a caller should use: an explicit ``kind_``; else the older ``frozen=`` flag
    (True meant the PyInstaller release); else the running process's ``kind()``."""
    if kind_ is not None:
        return kind_
    if frozen is not None:
        return PYINSTALLER if frozen else None
    return kind()


def _resolve_started_file(kind_: str | None = None, *, sys_module=None, main=None, argv0: str | None = None,
                          cwd: str | None = None, path: str | None = None, which=shutil.which,
                          exists=os.path.exists) -> str | None:
    """The file the user started, as they named it (symlinks kept), or None when it cannot be found.

    PyInstaller: ``sys.executable``. Nuitka: ``original_argv0``, absolute as it is,
    joined with the working directory at start when it has a separator, or looked
    up on the PATH at start when it is a bare name.
    """
    sys_module = sys if sys_module is None else sys_module
    kind_ = kind(sys_module, main) if kind_ is None else kind_
    if kind_ == PYINSTALLER:
        return getattr(sys_module, "executable", None) or None
    if kind_ != NUITKA:
        return None
    if argv0 is None:
        compiled = _compiled(sys_module, main)
        argv0 = getattr(compiled, "original_argv0", None) if compiled is not None else None
    if not argv0:
        return None
    cwd = _START_CWD if cwd is None else cwd
    if os.path.isabs(argv0):
        found = argv0
    elif os.sep in argv0 or (os.altsep and os.altsep in argv0):
        found = os.path.normpath(os.path.join(cwd, argv0))
    else:
        search_path = _START_PATH if path is None else path
        search_path = os.pathsep.join(entry if os.path.isabs(entry) else os.path.normpath(os.path.join(cwd, entry))
                                      for entry in search_path.split(os.pathsep))
        found = which(argv0, path=search_path)
        if found and not os.path.isabs(found):          # a relative PATH entry
            found = os.path.normpath(os.path.join(cwd, found))
    return found if found and exists(found) else None


_START_KIND = kind()
_STARTED_FILE = _resolve_started_file(_START_KIND)


def started_file(kind_: str | None = None, **inputs) -> str | None:
    """The launch path resolved at import, with symlinks kept; None if it could not be found.

    Explicit resolver inputs (sys_module, main, argv0, cwd, path, which, exists)
    run an independent lookup for tests; live callers use the captured result.
    """
    if not inputs and (kind_ is None or kind_ == _START_KIND):
        return _STARTED_FILE
    return _resolve_started_file(kind_, **inputs)


def data_dir(kind_: str | None = None, *, sys_module=None, main=None) -> str | None:
    """The folder the bundled files are in: ``sys._MEIPASS``, or the Nuitka main module's folder."""
    sys_module = sys if sys_module is None else sys_module
    kind_ = kind(sys_module, main) if kind_ is None else kind_
    if kind_ == PYINSTALLER:
        return getattr(sys_module, "_MEIPASS", None) or None
    if kind_ != NUITKA:
        return None
    if main is None:
        main = (getattr(sys_module, "modules", None) or {}).get("__main__")
    # containing_dir is beside the outer launcher, not inside the unpacked cache.
    return os.path.dirname(os.path.abspath(main.__file__)) if getattr(main, "__file__", None) else None


def cache_dir(kind_: str | None = None, *, sys_module=None, main=None) -> str | None:
    """The Nuitka build's cache folder (its data dir), kept between starts; None otherwise."""
    kind_ = kind(sys_module, main) if kind_ is None else kind_
    return data_dir(kind_, sys_module=sys_module, main=main) if kind_ == NUITKA else None


def relaunch_env(environ=None, kind_: str | None = None) -> dict:
    """A copy of ``environ`` for starting ``started_file()`` as a new instance, not a child of this run.

    PyInstaller: ``PYINSTALLER_RESET_ENVIRONMENT=1``. Nuitka: the onefile variables
    removed. Anything of the caller's own (``CAST_TV_DETACHED``) is left to the caller.
    """
    env = dict(os.environ if environ is None else environ)
    kind_ = kind() if kind_ is None else kind_
    if kind_ == PYINSTALLER:
        env[PYINSTALLER_RESET] = "1"
    elif kind_ == NUITKA:
        for key in list(env):
            upper = key.upper()                          # Windows names are case-insensitive
            if upper.startswith(NUITKA_ONEFILE_PREFIX) or upper == NUITKA_ORIGINAL_ARGV0:
                del env[key]
    return env


# ------------------------------------------------------------------ pruning
def _mtime(path: str) -> float | None:
    try:
        return os.stat(path).st_mtime
    except FileNotFoundError:
        return None


def _inside(image: str, folder: str) -> bool:
    folder = os.path.normcase(os.path.realpath(folder))
    image = os.path.normcase(os.path.realpath(image))
    return image == folder or image.startswith(folder.rstrip(os.sep) + os.sep)


def _prune_targets(current: str, limit: float) -> tuple[list[str], list[str]]:
    """A fresh retention decision. Unreadable metadata must propagate, never mean 'old'."""
    parent = os.path.dirname(current)
    names = os.listdir(parent)
    builds, leftovers = [], []
    for name in names:
        path = os.path.join(parent, name)
        if os.path.normcase(path) == os.path.normcase(current) or not os.path.isdir(path):
            continue
        if BUILD_ID.match(name):
            marker = _mtime(os.path.join(path, START_MARKER))
            builds.append((name, path, marker, marker if marker is not None else _mtime(path)))
        elif REMOVING.match(name):
            leftovers.append(path)

    previous = None
    marked = [b for b in builds if b[2] is not None]
    pool = marked or [b for b in builds if b[3] is not None]
    if pool:
        previous = max(pool, key=lambda b: (b[2] if marked else b[3], b[0]))[1]
    old = [b[1] for b in builds if b[1] != previous and b[3] is not None and b[3] <= limit]
    return old, leftovers


def prune_caches(cache_dir: str, processes=running_images, now=time.time, rename=os.rename,
                 remove=shutil.rmtree, min_age_days=7) -> list[str]:
    """Remove this release's old build folders beside ``cache_dir``; returns the folders removed.

    Kept: ``cache_dir`` (current), the previous build (the newest start marker among the
    others; without any marker, the newest modification time; a tie goes to the greater name),
    and every folder whose marker (or, without one, its modification time) is younger than
    ``min_age_days`` or that a running process's executable lies inside. Unreadable metadata
    or an incomplete process listing stops cleanup. Names outside the build identity grammar
    are never touched. Each deletion refreshes the evidence: a previous removal can be slow.
    """
    current = os.path.abspath(cache_dir)
    if not BUILD_ID.match(os.path.basename(current)):
        return []                                   # not a build folder of ours: touch nothing
    try:
        with open(os.path.join(current, START_MARKER), "ab"):
            pass
        started = now()
        os.utime(os.path.join(current, START_MARKER), (started, started))
        limit = started - min_age_days * 86400
        old, leftovers = _prune_targets(current, limit)
    except OSError:
        return []                                   # cannot prove age or record this start
    if not old and not leftovers:
        return []

    removed = []
    for path in old + leftovers:
        try:
            images = [image for _pid, image in processes()]
            eligible, unfinished = _prune_targets(current, limit)
        except (IncompleteListing, OSError):
            break                                   # stop if a later safety check becomes unreadable
        if path not in eligible and path not in unfinished:
            continue
        if any(_inside(image, path) for image in images):
            continue
        doomed = path
        if path in eligible:
            doomed = "%s.removing-%d" % (path, os.getpid())
            try:
                rename(path, doomed)                # Windows refuses while a file inside is locked
            except OSError:
                continue
        if _remove(doomed, remove):
            removed.append(path)
    return removed


def _remove(path: str, remove) -> bool:
    try:
        remove(path)
    except OSError:
        return False                                # what is left is finished on a later start
    return not os.path.exists(path)
