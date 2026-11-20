"""The packager facts: which packager, which file was started, where the data is, how to start again."""
import importlib.util
import os
import shutil
import sys
import types

import pytest

from castlib import bundle


def nuitka_main(tmp_path, argv0="/opt/cast-tv/cast-tv-linux-x64", onefile=True):
    """A main module as a Nuitka onefile child sees it: ``__compiled__`` and a ``__file__`` in the cache."""
    data = str(tmp_path / "cache" / "cast-tv" / "0.6.0-gh1.1")
    compiled = types.SimpleNamespace(onefile=onefile, containing_dir=str(tmp_path / "Downloads"),
                                     original_argv0=argv0)
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
    path = str(tmp_path / "system bin") + os.pathsep + str(tmp_path / "opt bin")

    def which(name, path=None):
        seen.append((name, path))
        return exe if path == str(tmp_path / "system bin") + os.pathsep + str(tmp_path / "opt bin") else None
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


@pytest.mark.parametrize("path_entry", ["bin", ".", ""])
def test_started_file_real_which_anchors_relative_path_to_start_cwd(tmp_path, monkeypatch, path_entry):
    start = tmp_path / "start"
    name = "cast-tv-test-binary" + (".exe" if sys.platform == "win32" else "")
    exe = _file(str(start / path_entry / name))
    os.chmod(exe, 0o755)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    found = bundle.started_file("nuitka", argv0=name, cwd=str(start), path=path_entry)
    assert found is not None
    assert os.path.normcase(found) == os.path.normcase(exe)


@pytest.mark.parametrize("present", [True, False])
def test_started_file_default_is_fixed_at_import(tmp_path, monkeypatch, present):
    start = tmp_path / "start"
    start.mkdir()
    name = "cast-tv-test-binary" + (".exe" if sys.platform == "win32" else "")
    exe = str(start / name)
    if present:
        _file(exe)
        os.chmod(exe, 0o755)
    monkeypatch.chdir(start)
    monkeypatch.setenv("PATH", ".")
    main = nuitka_main(tmp_path, argv0=name)
    monkeypatch.setitem(sys.modules, "__main__", main)
    spec = importlib.util.spec_from_file_location("startup_bundle", bundle.__file__)
    startup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(startup)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    if present:
        os.remove(exe)
    else:
        _file(exe)
        os.chmod(exe, 0o755)
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("PATH", str(elsewhere))
    main.__compiled__.original_argv0 = exe
    expected = exe if present else None
    assert startup.started_file() == expected
    assert startup.started_file("nuitka") == expected


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
    data = os.path.dirname(main.__file__)
    assert main.__compiled__.containing_dir != data       # the outer launcher's folder is not bundled data
    assert bundle.data_dir(sys_module=fake_sys(main)) == data
    assert bundle.cache_dir(sys_module=fake_sys(main)) == data
    no_dir = types.SimpleNamespace(__compiled__=types.SimpleNamespace(onefile=True), __file__=main.__file__)
    assert bundle.data_dir("nuitka", main=no_dir) == data                           # the main module's folder
    pyi = fake_sys(frozen=True, _MEIPASS="/tmp/_MEI1")
    assert bundle.data_dir(sys_module=pyi) == "/tmp/_MEI1"
    assert bundle.cache_dir(sys_module=pyi) is None                                 # unpacked anew every start
    assert bundle.data_dir(sys_module=fake_sys()) is None
    assert bundle.cache_dir(sys_module=fake_sys()) is None
    missing_main_file = types.SimpleNamespace(__compiled__=main.__compiled__)
    assert bundle.data_dir("nuitka", main=missing_main_file) is None


def test_nuitka_data_dir_is_the_long_path():
    """Windows hands the Nuitka child an 8.3 path (``C:\\Users\\RUNNER~1\\...\\050-GH~1.1``, PR #111's
    run 44628255344); the build folder is only recognised, and pruned, under its long name."""
    short = os.path.join("C:\\Users\\RUNNER~1\\AppData\\Local\\cast-tv\\050-GH~1.1", "entry.py")
    long_ = "C:\\Users\\runneradmin\\AppData\\Local\\cast-tv\\0.5.0-gh44628255344.1"
    main = types.SimpleNamespace(__compiled__=types.SimpleNamespace(onefile=True), __file__=short)
    seen = []
    expand = lambda p: seen.append(p) or long_                                    # noqa: E731
    assert bundle.data_dir("nuitka", main=main, long_path=expand) == long_
    assert bundle.cache_dir("nuitka", main=main, long_path=expand) == long_
    assert seen == [os.path.dirname(os.path.abspath(short))] * 2
    pyi = fake_sys(frozen=True, _MEIPASS="C:\\Users\\RUNNER~1\\Temp\\_MEI1")
    assert bundle.data_dir(sys_module=pyi, long_path=expand) == "C:\\Users\\RUNNER~1\\Temp\\_MEI1"   # as before
    assert bundle.data_dir("nuitka", main=main, long_path=lambda p: None) == os.path.dirname(os.path.abspath(short))


@pytest.mark.skipif(sys.platform != "win32", reason="8.3 names are a Windows file-system feature")
def test_long_path_expands_a_real_short_name(tmp_path):
    import ctypes
    folder = tmp_path / "0.5.0-gh44628255344.1"
    folder.mkdir()
    buf = ctypes.create_unicode_buffer(1024)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(folder), buf, 1024) or buf.value == str(folder):
        pytest.skip("this volume makes no 8.3 names")
    assert os.path.basename(buf.value) != folder.name
    assert os.path.normcase(bundle.long_path(buf.value)) == os.path.normcase(str(folder))
    assert bundle.long_path(str(tmp_path / "missing")) is None


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


# ----------------------------------------------------------------- pruning
DAY = 86400
NOW = 1_800_000_000.0


def build(parent, name, marker_days=None, mtime_days=None):
    """A build folder ``name``: a start marker ``marker_days`` old (None: no marker), its mtime ``mtime_days`` old."""
    folder = parent / name
    (folder / "sub").mkdir(parents=True, exist_ok=True)
    (folder / "sub" / "cast-tv.bin").write_text("x")
    if marker_days is not None:
        marker = folder / bundle.START_MARKER
        marker.write_text("")
        os.utime(marker, (NOW - marker_days * DAY,) * 2)
    if mtime_days is not None:
        os.utime(folder, (NOW - mtime_days * DAY,) * 2)
    return str(folder)


def prune(current, images=(), **kw):
    kw.setdefault("processes", lambda: [(100 + i, image) for i, image in enumerate(images)])
    kw.setdefault("now", lambda: NOW)
    return bundle.prune_caches(current, **kw)


def names(parent):
    return sorted(os.listdir(parent))


@pytest.fixture
def parent(tmp_path):
    p = tmp_path / "cache" / "cast-tv"
    p.mkdir(parents=True)
    return p


def test_prune_removes_the_oldest_of_three_builds(parent):
    oldest = build(parent, "0.6.0-gh1.1", marker_days=8)
    build(parent, "0.6.0-gh2.1", marker_days=3)
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current) == [oldest]
    assert names(parent) == ["0.6.0-gh2.1", "0.6.0-gh3.1"]
    assert os.stat(os.path.join(current, bundle.START_MARKER)).st_mtime == NOW     # this start is marked


def test_prune_keeps_a_folder_started_six_days_ago(parent):
    build(parent, "0.6.0-gh1.1", marker_days=6)
    build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current) == []
    assert len(names(parent)) == 3


def test_prune_the_age_guard_is_inclusive(parent):
    seven = build(parent, "0.6.0-gh1.1", marker_days=7)            # exactly 7 days: removable
    build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current) == [seven]


def test_prune_keeps_an_old_folder_in_use(parent):
    oldest = build(parent, "0.6.0-gh1.1", marker_days=30)
    build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current, images=[os.path.join(oldest, "sub", "cast-tv.bin")]) == []
    assert "0.6.0-gh1.1" in names(parent)


def test_prune_a_sibling_with_a_longer_name_is_not_in_use(parent):
    oldest = build(parent, "0.6.0-gh1.1", marker_days=30)
    build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current, images=[oldest + "0" + os.sep + "cast-tv.bin"]) == [oldest]


@pytest.mark.skipif(os.path.normcase("A") != "a", reason="paths are case-sensitive here")
def test_prune_in_use_ignores_case_on_windows(parent):
    oldest = build(parent, "0.6.0-gh1.1", marker_days=30)
    build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current, images=[os.path.join(oldest, "sub", "cast-tv.bin").upper()]) == []
    assert os.path.isdir(oldest)


def test_prune_an_incomplete_listing_removes_nothing(parent):
    build(parent, "0.6.0-gh1.1", marker_days=30)
    build(parent, "0.6.0-gh2.1", marker_days=1)
    (parent / "0.6.0-gh0.1.removing-9").mkdir()
    current = build(parent, "0.6.0-gh3.1")

    def incomplete():
        raise bundle.IncompleteListing("process 5 is ours but refused")
    assert prune(current, processes=incomplete) == []
    assert len(names(parent)) == 4


def test_prune_without_markers_uses_the_modification_time(parent):
    oldest = build(parent, "0.6.0-gh1.1", mtime_days=20)
    build(parent, "0.6.0-gh2.1", mtime_days=10)                # previous: the newest mtime, though old
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current) == [oldest]
    assert names(parent) == ["0.6.0-gh2.1", "0.6.0-gh3.1"]


def test_prune_marked_folders_win_over_unmarked_ones(parent):
    marked = build(parent, "0.6.0-gh1.1", marker_days=9, mtime_days=9)
    unmarked = build(parent, "0.6.0-gh2.1", mtime_days=8)       # newer mtime, but no marker
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current) == [unmarked]
    assert os.path.isdir(marked)                                 # the previous build


def test_prune_a_tie_in_the_marker_goes_to_the_greater_name(parent):
    lower = build(parent, "0.6.0-gh1.1", marker_days=10)
    build(parent, "0.6.0-gh1.2", marker_days=10)
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current) == [lower]


def test_prune_a_tie_in_the_mtime_goes_to_the_greater_name(parent):
    lower = build(parent, "0.6.0-gh1.1", mtime_days=10)
    build(parent, "0.6.0-local20261101120000", mtime_days=10)
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current) == [lower]


def test_prune_a_single_build(parent):
    current = build(parent, "0.6.0-gh3.1")
    listed = []
    assert prune(current, processes=lambda: listed.append(1) or []) == []
    assert listed == []                                          # nothing old: no listing needed
    assert names(parent) == ["0.6.0-gh3.1"]


def test_prune_never_touches_foreign_names(parent):
    for name in ("Cache", "0.5.0", "0.6.0-gh1", "0.6.0-local2026", "notes.removing-1",
                 "0.6.0-gh1.1.removing-x"):
        build(parent, name, marker_days=40, mtime_days=40)
    (parent / "0.6.0-gh9.9").write_text("a file, not a folder")
    build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current) == []
    assert len(names(parent)) == 9


def test_prune_does_nothing_from_a_folder_outside_the_grammar(parent):
    build(parent, "0.6.0-gh1.1", marker_days=30)
    build(parent, "0.6.0-gh2.1", marker_days=20)
    spike = build(parent, "0.5.0")
    assert prune(spike) == []
    assert len(names(parent)) == 3
    assert not os.path.exists(os.path.join(spike, bundle.START_MARKER))


def test_prune_a_rename_failure_keeps_the_folder(parent):
    oldest = build(parent, "0.6.0-gh1.1", marker_days=30)
    build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")
    removed = []

    def locked(src, dst):
        raise PermissionError(32, "a file inside is in use")
    assert prune(current, rename=locked, remove=removed.append) == []
    assert removed == []                                         # never deleted in place
    assert os.path.isdir(oldest)


def test_prune_deletes_only_the_renamed_copy(parent):
    oldest = build(parent, "0.6.0-gh1.1", marker_days=30)
    build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")
    removed = []

    def remove(path):
        removed.append(path)
        shutil.rmtree(path)
    assert prune(current, remove=remove) == [oldest]
    assert removed == ["%s.removing-%d" % (oldest, os.getpid())]


def test_prune_a_removal_error_is_ignored_and_finished_later(parent):
    oldest = build(parent, "0.6.0-gh1.1", marker_days=30)
    build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")

    def fails(path):
        raise OSError(13, "denied")
    assert prune(current, remove=fails) == []
    leftover = "0.6.0-gh1.1.removing-%d" % os.getpid()
    assert names(parent) == [leftover, "0.6.0-gh2.1", "0.6.0-gh3.1"]
    assert not os.path.exists(oldest)
    assert prune(current) == [str(parent / leftover)]            # the next start finishes it
    assert names(parent) == ["0.6.0-gh2.1", "0.6.0-gh3.1"]


def test_prune_finishes_a_leftover_from_an_earlier_run(parent):
    leftover = parent / "0.6.0-gh0.1.removing-4242"
    (leftover / "deep").mkdir(parents=True)
    (leftover / "deep" / "half.bin").write_text("x")
    build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current) == [str(leftover)]
    assert names(parent) == ["0.6.0-gh2.1", "0.6.0-gh3.1"]


def test_prune_keeps_a_leftover_still_in_use(parent):
    leftover = parent / "0.6.0-gh0.1.removing-4242"
    leftover.mkdir()
    current = build(parent, "0.6.0-gh3.1")
    assert prune(current, images=[str(leftover / "cast-tv.bin")]) == []
    assert leftover.is_dir()


@pytest.mark.parametrize("failure", [PermissionError, OSError])
def test_prune_an_unreadable_marker_does_not_fall_back_to_directory_age(parent, monkeypatch, failure):
    recent = build(parent, "0.6.0-gh1.1", marker_days=1, mtime_days=30)
    build(parent, "0.6.0-gh2.1", marker_days=0)
    current = build(parent, "0.6.0-gh3.1")
    stat = os.stat

    def unreadable(path, *args, **kwargs):
        if os.fspath(path) == os.path.join(recent, bundle.START_MARKER):
            raise failure("cannot read start marker")
        return stat(path, *args, **kwargs)

    monkeypatch.setattr(bundle.os, "stat", unreadable)
    assert prune(current) == []
    assert os.path.isdir(recent)


def test_prune_cannot_choose_previous_when_a_marker_is_unreadable(parent, monkeypatch):
    oldest = build(parent, "0.6.0-gh1.1", marker_days=30)
    previous = build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")
    stat = os.stat

    def unreadable(path, *args, **kwargs):
        if os.fspath(path) == os.path.join(previous, bundle.START_MARKER):
            raise PermissionError("cannot read previous marker")
        return stat(path, *args, **kwargs)

    monkeypatch.setattr(bundle.os, "stat", unreadable)
    assert prune(current) == []
    assert os.path.isdir(oldest) and os.path.isdir(previous)


def test_prune_requires_a_successfully_recorded_start(parent, monkeypatch):
    oldest = build(parent, "0.6.0-gh1.1", marker_days=30)
    build(parent, "0.6.0-gh2.1", marker_days=1)
    current = build(parent, "0.6.0-gh3.1")

    def unwritable(*args, **kwargs):
        raise PermissionError("cannot record this start")

    monkeypatch.setattr(bundle.os, "utime", unwritable)
    assert prune(current) == []
    assert os.path.isdir(oldest)


@pytest.mark.parametrize("leftover,change", [(False, "running"), (False, "started"),
                                          (False, "incomplete"), (True, "running"),
                                          (True, "incomplete")])
def test_prune_refreshes_safety_evidence_after_each_removal(parent, change, leftover):
    first = build(parent, "0.6.0-gh1.1", marker_days=30)
    second_name = "0.6.0-gh2.1" + (".removing-99" if leftover else "")
    second = build(parent, second_name, marker_days=29)
    build(parent, "0.6.0-gh3.1", marker_days=1)
    current = build(parent, "0.6.0-gh4.1")
    images = []
    incomplete = False
    protected = None

    def processes():
        if incomplete:
            raise bundle.IncompleteListing("a process became unreadable")
        return list(images)

    def remove(path):
        nonlocal incomplete, protected
        shutil.rmtree(path)
        if protected is not None:
            return
        # Either normal build may be visited first; directory iteration has no ordering contract.
        protected = second if path.startswith(first + ".removing-") else first
        if change == "running":
            images.append((77, os.path.join(protected, "sub", "cast-tv.bin")))
        elif change == "started":
            os.utime(os.path.join(protected, bundle.START_MARKER), (NOW, NOW))
        else:
            incomplete = True

    removed = prune(current, processes=processes, remove=remove)
    assert len(removed) == 1
    assert protected is not None and os.path.isdir(protected)
