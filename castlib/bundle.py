"""The packaged release: where a Nuitka build unpacks, and how its folders are named.

A Nuitka onefile release unpacks once into ``<cache root>/cast-tv/<build identity>`` and
reuses that folder on later starts (s16-faster-start). The build identity is
``<version>-gh<run id>.<run attempt>`` for a CI build or ``<version>-local<UTC
yyyymmddHHMMSS>`` for a local one: one grammar shared by the builder
(``packaging/build_nuitka.py``), the pruning of old folders and
``packaging/startup_time.py``. Nothing else under ``cast-tv`` (the GoPro browser's
``Cache`` folder on Windows) ever matches it.
"""
import os
import re
import sys

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
