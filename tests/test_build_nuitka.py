"""packaging/build_nuitka.py: the options, the identity, the pin and the provenance, without compiling (s16-faster-start)."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types

import pytest


@pytest.fixture
def bn():
    path = Path(__file__).resolve().parents[1] / "packaging" / "build_nuitka.py"
    spec = importlib.util.spec_from_file_location("cast_tv_build_nuitka", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def NOW():
    return datetime.datetime(2026, 11, 19, 21, 5, 9, tzinfo=datetime.timezone.utc)


COMMON = ["--onefile", "--onefile-tempdir-spec={CACHE_DIR}/cast-tv/0.6.0-gh7.2", "--product-name=cast-tv",
          "--product-version=0.6.0", "--file-version=0.6.0", "--include-package=castlib",
          "--include-package-data=castlib", "--include-package=pillow_heif", "--include-package-data=pillow_heif",
          "--nofollow-import-to=tkinter", "--nofollow-import-to=pytest", "--nofollow-import-to=gi"]


def test_windows_options(bn):
    out = os.path.join("dist", "cast-tv-windows-x64-nuitka.exe")
    opts = bn.options("0.6.0-gh7.2", out, "0.6.0", platform="win32")
    for opt in COMMON + ["--windows-console-mode=hide", "--windows-icon-from-ico=castlib/ui/cast-tv.ico",
                         "--include-module=webview.platforms.winforms",
                         "--output-dir=dist", "--output-filename=cast-tv-windows-x64-nuitka.exe"]:
        assert opt in opts
    assert opts[-1] == "packaging/entry.py"
    assert not [o for o in opts if "pyside6" in o or "qtpy" in o or ".qt" in o or "fonts.conf" in o
                or "noinclude-dlls" in o]


def test_linux_options(bn):
    out = os.path.join("dist", "cast-tv-linux-x64-nuitka")
    opts = bn.options("0.6.0-gh7.2", out, "0.6.0", platform="linux")
    for opt in COMMON + ["--enable-plugins=pyside6", "--include-module=webview.platforms.qt",
                         "--include-module=qtpy", "--noinclude-dlls=libgbm.so*", "--noinclude-dlls=libstdc++.so*",
                         "--include-data-files=packaging/fonts.conf=fontconfig/fonts.conf",
                         "--output-dir=dist", "--output-filename=cast-tv-linux-x64-nuitka"]:
        assert opt in opts
    assert opts[-1] == "packaging/entry.py"
    assert not [o for o in opts if o.startswith("--windows-") or "winforms" in o or o.startswith("--msvc")]


def test_other_systems_are_refused(bn):
    with pytest.raises(bn.BuildError):
        bn.options("0.6.0-gh7.2", "dist/x", "0.6.0", platform="darwin")


def test_identity_from_build_id_ci_variables_or_local(bn):
    ci = {"GITHUB_RUN_ID": "19123456789", "GITHUB_RUN_ATTEMPT": "2"}
    assert bn.build_identity("0.6.0", "gh5.1", environ=ci) == "0.6.0-gh5.1"          # --build-id wins
    assert bn.build_identity("0.6.0", environ=ci) == "0.6.0-gh19123456789.2"
    assert bn.build_identity("0.6.0", environ={}, now=NOW) == "0.6.0-local20261119210509"
    assert bn.build_identity("0.6.0", environ={"GITHUB_RUN_ID": "1"}, now=NOW) == "0.6.0-local20261119210509"


@pytest.mark.parametrize("version,build_id", [("0.6.0", "gh5"), ("0.6.0", "local2026"), ("0.6.0", "../x"),
                                              ("0.6", "gh5.1"), ("0.6.0", "Cache")])
def test_identity_outside_the_grammar_is_refused(bn, version, build_id):
    with pytest.raises(bn.BuildError):
        bn.build_identity(version, build_id, environ={})


FREEZE = "nuitka==4.3.5\npywebview==6.2.1\n"


def _main(bn, tmp_path, argv, version="4.3.5", returncode=0, write=True):
    calls = []
    out = tmp_path / "cast-tv-nuitka"

    def run(cmd, cwd=None):
        calls.append((cmd, cwd))
        if write:
            out.write_bytes(b"binary")
        return types.SimpleNamespace(returncode=returncode)
    code = bn.main(["--out", str(out)] + argv, run=run, nuitka_version=lambda: version,
                   freeze=lambda: FREEZE, commit=lambda environ: "abc123",
                   environ={"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"}, now=NOW, platform="linux")
    return code, calls, out


@pytest.mark.parametrize("version", ["4.3.4", "4.4.0", None])
def test_any_other_nuitka_version_is_refused(bn, tmp_path, version, capsys):
    code, calls, out = _main(bn, tmp_path, [], version=version)
    assert code == 2 and calls == []
    assert "Nuitka 4.3.5 is required" in capsys.readouterr().err
    assert not Path(str(out) + ".build-info.json").exists()


def test_a_bad_build_id_compiles_nothing(bn, tmp_path):
    code, calls, _out = _main(bn, tmp_path, ["--build-id", "gh7"])
    assert code == 2 and calls == []


def test_provenance_file(bn, tmp_path):
    code, calls, out = _main(bn, tmp_path, [])
    assert code == 0
    (cmd, cwd), = calls
    assert cmd[:3] == [sys.executable, "-m", "nuitka"] and cwd == bn.ROOT
    info = json.loads(Path(str(out) + ".build-info.json").read_text(encoding="utf-8"))
    identity = bn.castlib.__version__ + "-gh7.2"
    assert info["identity"] == identity
    assert info["cache"] == "{CACHE_DIR}/cast-tv/" + identity
    assert info["nuitka"] == "4.3.5"
    assert info["python"] == sys.version
    assert info["pip_freeze_sha256"] == hashlib.sha256(FREEZE.encode()).hexdigest()
    assert info["commit"] == "abc123"
    assert info["options"] == cmd[3:]
    assert "--onefile-tempdir-spec={CACHE_DIR}/cast-tv/" + identity in info["options"]


@pytest.mark.parametrize("returncode,write", [(1, False), (0, False)])
def test_a_failed_build_writes_no_provenance(bn, tmp_path, returncode, write):
    code, _calls, out = _main(bn, tmp_path, [], returncode=returncode, write=write)
    assert code != 0
    assert not Path(str(out) + ".build-info.json").exists()
