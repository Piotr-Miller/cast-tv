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

Every function takes its inputs as parameters, so tests can stand in for
either packager; the defaults read the running process at call time.
"""
from __future__ import annotations

import os
import re
import shutil
import sys

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


def started_file(kind_: str | None = None, *, sys_module=None, main=None, argv0: str | None = None,
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
    if os.path.isabs(argv0):
        found = argv0
    elif os.sep in argv0 or (os.altsep and os.altsep in argv0):
        found = os.path.normpath(os.path.join(_START_CWD if cwd is None else cwd, argv0))
    else:
        found = which(argv0, path=_START_PATH if path is None else path)
        if found and not os.path.isabs(found):          # a relative PATH entry
            found = os.path.normpath(os.path.join(_START_CWD if cwd is None else cwd, found))
    return found if found and exists(found) else None


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
    compiled = getattr(main, "__compiled__", None)
    folder = getattr(compiled, "containing_dir", None)
    if not folder and getattr(main, "__file__", None):
        folder = os.path.dirname(os.path.abspath(main.__file__))
    return folder or None


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
