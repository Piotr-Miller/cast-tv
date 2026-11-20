"""Build the Nuitka onefile release of cast-tv for the running system (s16-faster-start).

    python packaging/build_nuitka.py --out dist/cast-tv-linux-x64 [--build-id gh123.1]

The release file, built from ``packaging/entry.py`` with the window extra installed; it carries
what the PyInstaller spec it replaced carried (deleted in s16-faster-start Phase 6). The file unpacks once into
``{CACHE_DIR}/cast-tv/<build identity>`` and reuses that folder on later starts.

The build identity is ``<version>-<build>``: ``<build>`` is ``--build-id``, else
``gh<GITHUB_RUN_ID>.<GITHUB_RUN_ATTEMPT>`` in CI, else ``local<UTC yyyymmddHHMMSS>``. It must
match the grammar ``castlib.bundle.BUILD_ID`` shares with the pruning and the measuring script.

Windows: the WinForms backend (WebView2), the console hidden on a double-click
(``--windows-console-mode=hide``, the counterpart of PyInstaller's ``hide-early``), the icon.
Linux: the PySide6 plugin and the Qt backend, the host's libgbm and libstdc++ (the bundled
ones break Qt WebEngine's GPU path), and the private Fontconfig rules.

Nuitka is pinned: the build refuses any version but ``NUITKA_VERSION``. Next to the file it
writes ``<out>.build-info.json``: the identity, the Nuitka and Python versions, the hash of
``pip freeze``, the commit and the exact option list, so a published file can be shown to be
equivalent to a measured one.
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)                              # castlib from the checkout

import castlib                                            # noqa: E402
from castlib import bundle                                # noqa: E402

NUITKA_VERSION = "4.3.5"
ENTRY = "packaging/entry.py"


class BuildError(Exception):
    """The build cannot go ahead as asked (exit 2)."""


def build_identity(version: str, build_id: str | None = None, environ=None, now=None) -> str:
    """``<version>-<build>``, validated against the shared grammar."""
    environ = os.environ if environ is None else environ
    if build_id is None:
        run_id, attempt = environ.get("GITHUB_RUN_ID"), environ.get("GITHUB_RUN_ATTEMPT")
        if run_id and attempt:
            build_id = "gh%s.%s" % (run_id, attempt)
        else:
            moment = now() if now else datetime.datetime.now(datetime.timezone.utc)
            build_id = "local" + moment.strftime("%Y%m%d%H%M%S")
    identity = "%s-%s" % (version, build_id)
    if not bundle.BUILD_ID.match(identity):
        raise BuildError("build identity %r does not match %s" % (identity, bundle.BUILD_ID.pattern))
    return identity


def options(identity: str, out: str, version: str, platform: str | None = None) -> list[str]:
    """Nuitka's arguments for this system, the entry script last. Paths are relative to the checkout."""
    platform = platform or sys.platform
    folder, name = os.path.split(out)
    opts = [
        "--onefile",
        "--onefile-tempdir-spec={CACHE_DIR}/%s/%s" % (bundle.APP_DIR, identity),
        "--assume-yes-for-downloads",
        "--product-name=cast-tv",
        "--product-version=" + version,
        "--file-version=" + version,
        "--include-package=castlib", "--include-package-data=castlib",
        "--include-package=pillow_heif", "--include-package-data=pillow_heif",
        "--nofollow-import-to=tkinter", "--nofollow-import-to=pytest",
        "--nofollow-import-to=gi",                        # a host GTK must never be collected
    ]
    if platform == "win32":
        opts += [
            "--msvc=latest",
            "--windows-console-mode=hide",
            "--windows-icon-from-ico=castlib/ui/cast-tv.ico",
            "--include-module=webview.platforms.winforms",
        ]
    elif platform.startswith("linux"):
        opts += [
            "--enable-plugins=pyside6",
            "--include-module=webview.platforms.qt", "--include-module=qtpy",
            # the bundled copies break Qt WebEngine's GPU path on current distributions
            # (s12-desktop-window, research.md, 2026-10-16); every distribution has its own
            "--noinclude-dlls=libgbm.so*", "--noinclude-dlls=libstdc++.so*",
            # the private Fontconfig rules, found by castlib.platform.use_bundled_font_config
            "--include-data-files=packaging/fonts.conf=fontconfig/fonts.conf",
        ]
    else:
        raise BuildError("no release build for %s" % platform)
    opts += ["--output-dir=" + (folder or "."), "--output-filename=" + name, ENTRY]
    return opts


def installed_nuitka_version() -> str | None:
    try:
        from nuitka.Version import getNuitkaVersion
    except ImportError:
        return None
    return getNuitkaVersion()


def pip_freeze() -> str:
    return subprocess.run([sys.executable, "-m", "pip", "freeze", "--all"], capture_output=True,
                          text=True, check=True).stdout


def git_commit(environ=None) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    except OSError:
        out = None
    if out is not None and out.returncode == 0 and out.stdout.strip():
        return out.stdout.strip()
    return (os.environ if environ is None else environ).get("GITHUB_SHA") or None


def provenance(identity: str, opts: list[str], *, nuitka: str, freeze: str, commit: str | None) -> dict:
    return {
        "identity": identity,
        "cache": "{CACHE_DIR}/%s/%s" % (bundle.APP_DIR, identity),
        "nuitka": nuitka,
        "python": sys.version,
        "platform": sys.platform,
        "pip_freeze_sha256": hashlib.sha256(freeze.encode("utf-8")).hexdigest(),
        "pip_freeze": freeze.splitlines(),
        "commit": commit,
        "options": opts,
    }


def main(argv=None, *, run=subprocess.run, nuitka_version=installed_nuitka_version, freeze=pip_freeze,
         commit=git_commit, environ=None, now=None, platform=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="the file to build, e.g. dist/cast-tv-linux-x64")
    ap.add_argument("--build-id", help="the <build> part of the identity (gh<run>.<attempt> or local<14 digits>)")
    args = ap.parse_args(argv)
    try:
        found = nuitka_version()
        if found != NUITKA_VERSION:
            raise BuildError("Nuitka %s is required, found %s: python -m pip install nuitka==%s"
                             % (NUITKA_VERSION, found or "none", NUITKA_VERSION))
        version = castlib.__version__
        identity = build_identity(version, args.build_id, environ=environ, now=now)
        out = os.path.abspath(args.out)
        opts = options(identity, out, version, platform)
    except BuildError as e:
        print("build_nuitka: %s" % e, file=sys.stderr)
        return 2
    print("Building %s, cache folder {CACHE_DIR}/%s/%s" % (out, bundle.APP_DIR, identity), flush=True)
    result = run([sys.executable, "-m", "nuitka", *opts], cwd=ROOT)
    if result.returncode != 0:
        print("build_nuitka: Nuitka failed (%d)" % result.returncode, file=sys.stderr)
        return result.returncode or 1
    if not os.path.isfile(out):
        print("build_nuitka: Nuitka finished but %s is missing" % out, file=sys.stderr)
        return 1
    info = provenance(identity, opts, nuitka=found, freeze=freeze(), commit=commit(environ))
    with open(out + ".build-info.json", "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2)
        fh.write("\n")
    print("Built %s (%d bytes), %s.build-info.json" % (out, os.path.getsize(out), out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
