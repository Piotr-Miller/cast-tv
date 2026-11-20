"""packaging/startup_time.py: the logic around a timed start, without starting anything (s16-faster-start)."""
import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def st():
    path = Path(__file__).resolve().parents[1] / "packaging" / "startup_time.py"
    spec = importlib.util.spec_from_file_location("cast_tv_startup_time", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PARENT = os.path.abspath(os.path.join("cache-root", "cast-tv"))
BINARY = os.path.abspath(os.path.join("dl", "cast-tv-linux-x64-nuitka"))


def test_median(st):
    assert st.median([3.0, 1.0, 2.0, 5.0, 4.0]) == 3.0
    assert st.median([1.0, 4.0]) == 2.5


@pytest.mark.parametrize("image,expected", [
    (os.path.join("x", "cast-tv-windows-x64.exe"), True),            # a release or its bootstrap
    (os.path.join(PARENT, "0.6.0-gh1.1", "entry.exe"), True),        # a cached child, whatever its name
    (BINARY, True),
    (os.path.join("x", "python.exe"), False),
    (PARENT + "-other" + os.sep + "y.exe", False),                    # a sibling folder that merely shares the prefix
])
def test_what_counts_as_cast_tv(st, image, expected):
    assert st.is_cast_tv(image, BINARY, PARENT) is expected


def test_preflight_refuses_another_instance_on_another_port(st):
    images = lambda: [(77, os.path.join(PARENT, "0.6.0-gh1.1", "entry.exe"))]
    with pytest.raises(st.Refused, match="77"):
        st.preflight(BINARY, images=images, answers=lambda: False, parent=PARENT)


def test_preflight_refuses_a_bootstrap_still_unpacking(st):
    images = lambda: [(78, os.path.join("Downloads", "cast-tv-linux-x64"))]
    with pytest.raises(st.Refused):
        st.preflight(BINARY, images=images, answers=lambda: False, parent=PARENT)


def test_preflight_refuses_something_on_the_default_port(st):
    with pytest.raises(st.Refused, match="8895"):
        st.preflight(BINARY, images=lambda: [], answers=lambda: True, parent=PARENT)


def test_preflight_refuses_an_incomplete_list(st):
    def images():
        raise st.IncompleteListing("process 5 is ours but unreadable")
    with pytest.raises(st.Refused, match="incomplete"):
        st.preflight(BINARY, images=images, answers=lambda: False, parent=PARENT)


def test_preflight_waits_for_the_last_run_to_go(st):
    seen = [[(9, BINARY)], [(9, BINARY)], []]
    now = [0.0]
    st.preflight(BINARY, images=lambda: seen.pop(0), answers=lambda: False, parent=PARENT, wait=30,
                 clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    assert seen == [] and now[0] == 1.0


def test_cache_line(st):
    assert st.cache_from_version("cast-tv 0.6.0\nCache: /home/u/.cache/cast-tv/0.6.0-gh1.1\n") == \
        "/home/u/.cache/cast-tv/0.6.0-gh1.1"
    assert st.cache_from_version("cast-tv 0.6.0\nCache: none\n") is None
    assert st.cache_from_version("cast-tv 0.5.0\nWindow: edgechromium\n") is None


def test_cold_clears_only_a_validated_build_folder(st, tmp_path):
    removed = []
    folder = str(tmp_path / "0.6.0-gh1.1")
    os.mkdir(folder)
    st.clear_cache(folder, valid=lambda p: True, remove=removed.append)
    assert removed == [folder]
    with pytest.raises(st.Refused):
        st.clear_cache(str(tmp_path / "Cache"), valid=lambda p: False, remove=removed.append)
    st.clear_cache(None, valid=lambda p: pytest.fail("PyInstaller has no folder"), remove=removed.append)
    assert removed == [folder]


def test_the_real_validation_accepts_only_build_folders(tmp_path, monkeypatch):
    from castlib import bundle
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    parent = bundle.cache_parent()
    assert bundle.is_build_folder(os.path.join(parent, "0.6.0-gh123.2"))
    assert bundle.is_build_folder(os.path.join(parent, "0.6.0-local20261118193000"))
    for bad in ("Cache", "0.5.0", "0.6.0-1a2b3c4", "0.6.0-gh123", "x/0.6.0-gh1.1"):
        assert not bundle.is_build_folder(os.path.join(parent, bad)), bad
    assert not bundle.is_build_folder(os.path.join(str(tmp_path), "0.6.0-gh1.1"))   # not under cast-tv


class Proc:
    pid = 500

    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode


def _measure(st, statuses, **kw):
    proc = Proc()
    stopped = []
    now = [100.0]
    answers = iter(statuses)

    def status(port):
        value = next(answers)
        if isinstance(value, Exception):
            raise value
        return value

    seconds = st.measure_once(BINARY, port=4000, popen=lambda *a, **k: proc, status=status,
                              stop=lambda p, port, inst: stopped.append(inst) or True, owns=lambda p, inst: inst["pid"] == 500,
                              clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s), **kw)
    return seconds, stopped


def test_a_run_waits_for_both_marks(st):
    base = {"id": "i", "pid": 500, "parent_pid": 1}
    seconds, stopped = _measure(st, [OSError("not yet"),
                                     {"instance": dict(base, ui_ready_at=None, shown_at=101.0)},
                                     {"instance": dict(base, ui_ready_at=102.5, shown_at=101.0)}])
    assert seconds == pytest.approx(2.5)
    assert stopped and stopped[0]["id"] == "i"


def test_a_watched_run_prints_at_once_and_holds_the_window(st):
    base = {"id": "i", "pid": 500, "parent_pid": 1}
    said = []
    seconds, stopped = _measure(st, [{"instance": dict(base, ui_ready_at=101.0, shown_at=101.5)}],
                                hold=10, out=said.append)
    assert seconds == pytest.approx(1.5)                  # the hold is not part of the time
    assert said == ["ready after 1.50 s: the window stays open 10 s"] and len(stopped) == 1


def test_a_file_without_the_mark_says_so(st):
    with pytest.raises(st.NoReadyMark):
        _measure(st, [{"instance": {"id": "i", "pid": 500, "parent_pid": 1}}])


def test_a_run_that_never_gets_ready_fails(st):
    base = {"id": "i", "pid": 500, "parent_pid": 1, "ui_ready_at": None, "shown_at": None}
    with pytest.raises(st.RunFailed):
        _measure(st, [{"instance": base}] * 100, timeout=1.0)


def test_another_process_on_the_port_is_refused(st):
    with pytest.raises(st.Refused):
        _measure(st, [{"instance": {"id": "x", "pid": 9, "parent_pid": 1, "ui_ready_at": 1.0, "shown_at": 1.0}}])


@pytest.mark.parametrize("cleanup", [False, OSError("stop failed")])
@pytest.mark.parametrize("missing_mark", [False, True])
def test_cleanup_failure_rejects_success_but_preserves_an_earlier_error(st, cleanup, missing_mark):
    proc = Proc()
    instance = {"id": "i", "pid": 500}
    if not missing_mark:
        instance.update(ui_ready_at=102., shown_at=101.)
    stopped = []

    def stop(*args):
        stopped.append(args)
        if isinstance(cleanup, Exception):
            raise cleanup
        return cleanup

    with pytest.raises(st.NoReadyMark if missing_mark else st.RunFailed):
        st.measure_once(BINARY, port=4000, popen=lambda *a, **k: proc,
                        status=lambda p: {"instance": instance}, owns=lambda *a: True,
                        stop=stop, clock=lambda: 100.)
    assert len(stopped) == 1


@pytest.mark.parametrize("failure", ["nonzero", "oserror", "timeout"])
def test_failed_version_probe_never_measures_or_writes_results(st, monkeypatch, tmp_path, failure):
    import subprocess
    from types import SimpleNamespace

    def run(*args, **kw):
        if failure == "oserror":
            raise OSError("cannot launch")
        if failure == "timeout":
            raise subprocess.TimeoutExpired([BINARY, "--version"], 180)
        return SimpleNamespace(returncode=7, stdout="", stderr="version failed")

    monkeypatch.setattr(st, "preflight", lambda b: None)
    monkeypatch.setattr(st.subprocess, "run", run)
    monkeypatch.setattr(st, "run_series", lambda *a, **k: pytest.fail("measured after failed version"))
    out = tmp_path / "result.json"
    assert st.main([BINARY, "--mode", "cold", "--out", str(out)]) == 1
    assert not out.exists()


def test_successful_legacy_version_probe_can_reach_missing_mark_detection(st, monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(st, "preflight", lambda b: None)
    monkeypatch.setattr(st.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout="cast-tv 0.5.0\n", stderr=""))

    def series(*args, version_text, **kw):
        assert st.cache_from_version(version_text) is None
        raise st.NoReadyMark("this build has no Ready mark (built before s16-faster-start)")

    monkeypatch.setattr(st, "run_series", series)
    out = tmp_path / "result.json"
    assert st.main([BINARY, "--mode", "cold", "--out", str(out)]) == 3
    assert not out.exists()


def test_warm_primes_once_and_cold_clears_before_every_run(st):
    calls = []
    measured = iter([3.0, 2.0, 4.0])
    common = dict(measure=lambda b: calls.append("run") or next(measured),
                  check=lambda b, wait: calls.append("check"), out=lambda s: None,
                  prime=lambda b: calls.append("prime") or 9.0)
    warm = st.run_series(BINARY, "warm", 3, version_text="Cache: none", clear=lambda f: calls.append("clear"), **common)
    assert warm == [3.0, 2.0, 4.0] and calls.count("clear") == 0
    assert calls[:2] == ["check", "prime"] and calls.count("run") == 3   # the held (watched) measure never primes
    calls.clear()
    measured = iter([5.0, 6.0])
    common["measure"] = lambda b: calls.append("run") or next(measured)
    cold = st.run_series(BINARY, "cold", 2, version_text="Cache: /c/cast-tv/0.6.0-gh1.1",
                         clear=lambda f: calls.append("clear " + f), **common)
    assert cold == [5.0, 6.0]
    assert calls == ["check", "clear /c/cast-tv/0.6.0-gh1.1", "run", "check", "clear /c/cast-tv/0.6.0-gh1.1", "run"]


@pytest.mark.parametrize("mode,nuitka,expected", [
    ("warm", 2.0, True),          # exactly half passes
    ("warm", 2.01, False),
    ("cold", 4.0, True),          # an equal cold median passes
    ("cold", 4.01, False),
])
def test_compare_against_the_bar(st, mode, nuitka, expected):
    a = {"mode": mode, "system": "Linux", "median": nuitka}
    b = {"mode": mode, "system": "Linux", "median": 4.0}
    lines, ok = st.compare(a, b, 0.5)
    assert ok is expected and ("PASS" if expected else "FAIL") in lines[0]


def test_compare_refuses_mismatched_results(st):
    with pytest.raises(ValueError):
        st.compare({"mode": "warm", "system": "Linux", "median": 1}, {"mode": "cold", "system": "Linux", "median": 1}, 0.5)
