"""The packager facts: which packager, which file was started, where the data is, how to start again."""
import os
import sys
import types

import pytest

from castlib import bundle


def nuitka_main(tmp_path, argv0="/opt/cast-tv/cast-tv-linux-x64", onefile=True):
    """A main module as a Nuitka onefile child sees it: ``__compiled__`` and a ``__file__`` in the cache."""
    data = str(tmp_path / "cache" / "cast-tv" / "0.6.0-gh1.1")
    compiled = types.SimpleNamespace(onefile=onefile, containing_dir=data, original_argv0=argv0)
    return types.SimpleNamespace(__compiled__=compiled, __file__=os.path.join(data, "entry.py"))


def fake_sys(main=None, **kw):
    return types.SimpleNamespace(modules={"__main__": main} if main is not None else {}, **kw)


# ------------------------------------------------------------------ kind
def test_the_three_kinds(tmp_path):
    assert bundle.kind(fake_sys()) is None                                         # a checkout or pipx
    assert bundle.kind(fake_sys(frozen=True, _MEIPASS="/tmp/_MEI1")) == "pyinstaller"
    assert bundle.kind(fake_sys(nuitka_main(tmp_path))) == "nuitka"
    assert bundle.kind(fake_sys(nuitka_main(tmp_path, onefile=False))) is None      # Nuitka, but no onefile release
    assert bundle.kind(main=nuitka_main(tmp_path)) == "nuitka"
    assert bundle.kind() is None                                                   # this test run


def test_resolve_kind_keeps_the_frozen_flag(monkeypatch):
    assert bundle.resolve_kind("nuitka", frozen=False) == "nuitka"
    assert bundle.resolve_kind(None, frozen=True) == "pyinstaller"
    assert bundle.resolve_kind(None, frozen=False) is None
    monkeypatch.setattr(bundle, "kind", lambda: "nuitka")
    assert bundle.resolve_kind() == "nuitka"


# ------------------------------------------------------------ started_file
def _file(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("")
    return path


def test_started_file_pyinstaller_is_sys_executable():
    assert bundle.started_file("pyinstaller", sys_module=fake_sys(executable="C:\\x\\cast-tv.exe")) == \
        "C:\\x\\cast-tv.exe"
    assert bundle.started_file(None, sys_module=fake_sys()) is None                # not a release


def test_started_file_absolute(tmp_path):
    exe = _file(str(tmp_path / "Apps" / "cast tv" / "cast-tv-linux-x64"))        # a path with spaces
    main = nuitka_main(tmp_path, argv0=exe)
    assert bundle.started_file(sys_module=fake_sys(main)) == exe
    assert bundle.started_file("nuitka", main=main) == exe


def test_started_file_relative_from_the_start_directory(tmp_path, monkeypatch):
    exe = _file(str(tmp_path / "down loads" / "cast-tv-linux-x64"))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)                       # the working directory changed after the start
    rel = os.path.join("down loads", "cast-tv-linux-x64")
    assert bundle.started_file("nuitka", argv0=rel, cwd=str(tmp_path)) == exe
    assert bundle.started_file("nuitka", argv0=os.path.join(".", rel), cwd=str(tmp_path)) == exe
    assert bundle.started_file("nuitka", argv0=rel, cwd=str(elsewhere)) is None


def test_started_file_relative_uses_the_directory_captured_at_import(tmp_path, monkeypatch):
    exe = _file(str(tmp_path / "bin" / "cast-tv-linux-x64"))
    monkeypatch.setattr(bundle, "_START_CWD", str(tmp_path))
    monkeypatch.chdir(tmp_path / "bin")
    assert bundle.started_file("nuitka", argv0=os.path.join("bin", "cast-tv-linux-x64")) == exe


def test_started_file_bare_name_on_the_start_path(tmp_path, monkeypatch):
    exe = _file(str(tmp_path / "opt bin" / "cast-tv-linux-x64"))
    os.chmod(exe, 0o755)
    seen = []

    def which(name, path=None):
        seen.append((name, path))
        return exe if path == "/usr/bin" + os.pathsep + str(tmp_path / "opt bin") else None
    path = "/usr/bin" + os.pathsep + str(tmp_path / "opt bin")
    assert bundle.started_file("nuitka", argv0="cast-tv-linux-x64", path=path, which=which) == exe
    assert seen == [("cast-tv-linux-x64", path)]
    monkeypatch.setattr(bundle, "_START_PATH", path)               # the PATH at import, not today's
    monkeypatch.setenv("PATH", "/nowhere")
    assert bundle.started_file("nuitka", argv0="cast-tv-linux-x64", which=which) == exe


def test_started_file_bare_name_with_the_real_which(tmp_path):
    name = "cast-tv-test-binary" + (".exe" if sys.platform == "win32" else "")
    exe = _file(str(tmp_path / "on path" / name))
    os.chmod(exe, 0o755)
    assert os.path.normcase(bundle.started_file("nuitka", argv0=name, path=str(tmp_path / "on path"))) == \
        os.path.normcase(exe)


def test_started_file_bare_name_on_a_relative_path_entry(tmp_path):
    exe = _file(str(tmp_path / "bin" / "cast-tv-linux-x64"))
    which = lambda name, path=None: os.path.join("bin", name)       # noqa: E731 - PATH held "bin"
    assert bundle.started_file("nuitka", argv0="cast-tv-linux-x64", cwd=str(tmp_path), path="bin",
                               which=which) == exe


def test_started_file_keeps_a_symlink(tmp_path):
    real = _file(str(tmp_path / "real" / "cast-tv-linux-x64"))
    link = str(tmp_path / "cast-tv")
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symlinks")
    assert bundle.started_file("nuitka", argv0=link) == link
    assert bundle.started_file("nuitka", argv0="cast-tv", cwd=str(tmp_path), path=str(tmp_path),
                               which=lambda n, path=None: os.path.join(path, n)) == link


def test_started_file_missing(tmp_path):
    gone = str(tmp_path / "moved away" / "cast-tv-linux-x64")
    assert bundle.started_file("nuitka", argv0=gone) is None
    assert bundle.started_file("nuitka", argv0="cast-tv-linux-x64", which=lambda n, path=None: None) is None
    assert bundle.started_file("nuitka", argv0="") is None
    assert bundle.started_file("nuitka", sys_module=fake_sys()) is None              # no __compiled__ at all


# ------------------------------------------------------- data and cache dirs
def test_data_dir_and_cache_dir_per_kind(tmp_path):
    main = nuitka_main(tmp_path)
    data = main.__compiled__.containing_dir
    assert bundle.data_dir(sys_module=fake_sys(main)) == data
    assert bundle.cache_dir(sys_module=fake_sys(main)) == data
    no_dir = types.SimpleNamespace(__compiled__=types.SimpleNamespace(onefile=True), __file__=main.__file__)
    assert bundle.data_dir("nuitka", main=no_dir) == data                           # the main module's folder
    pyi = fake_sys(frozen=True, _MEIPASS="/tmp/_MEI1")
    assert bundle.data_dir(sys_module=pyi) == "/tmp/_MEI1"
    assert bundle.cache_dir(sys_module=pyi) is None                                 # unpacked anew every start
    assert bundle.data_dir(sys_module=fake_sys()) is None
    assert bundle.cache_dir(sys_module=fake_sys()) is None


# ------------------------------------------------------------- relaunch_env
NUITKA_CHILD = {
    "PATH": "/usr/bin", "CAST_TV_DETACHED": "1",
    "NUITKA_ONEFILE_PARENT": "4242", "NUITKA_ONEFILE_DIRECTORY": "/opt/cast-tv",
    "NUITKA_ORIGINAL_ARGV0": "cast-tv-linux-x64", "NUITKA_ONEFILE_START": "1",
    "Nuitka_Onefile_Time_Us": "5",
}


def test_relaunch_env_per_kind():
    source = dict(NUITKA_CHILD)
    assert bundle.relaunch_env(source, "nuitka") == {"PATH": "/usr/bin", "CAST_TV_DETACHED": "1"}
    assert source == NUITKA_CHILD                                                   # a copy
    pyi = bundle.relaunch_env({"PATH": "/usr/bin"}, "pyinstaller")
    assert pyi == {"PATH": "/usr/bin", "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    assert bundle.relaunch_env({"PATH": "/usr/bin", "NUITKA_ONEFILE_PARENT": "1"}, None) == \
        {"PATH": "/usr/bin", "NUITKA_ONEFILE_PARENT": "1"}                          # not a release: unchanged
