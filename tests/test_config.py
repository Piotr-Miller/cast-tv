import json
import os

import pytest

from castlib import config
from castlib.errors import ConfigError


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_CACHE", str(tmp_path / "cache"))
    return tmp_path / "cache"


def test_cache_name_must_be_bare(cache):
    for bad in ("../x", "a/b", "", ".", "..", "a\\b"):
        with pytest.raises(ConfigError):
            config.cache_write(bad, {})
        with pytest.raises(ConfigError):
            config.cache_read(bad)


def test_cache_write_is_atomic_and_readable(cache):
    config.cache_write("list.json", [1, 2])
    assert config.cache_read("list.json") == [1, 2]
    assert sorted(os.listdir(cache)) == ["list.json"]
    assert config.cache_read("missing.json") is None


def _boom(*a, **k):
    raise OSError("disk says no")


def test_write_json_cleans_up_when_dump_fails(tmp_path):
    path = tmp_path / "d" / "s.json"
    config.write_json(str(path), {"a": 1})
    with pytest.raises(TypeError):
        config.write_json(str(path), {"a": object()})       # not serialisable
    assert os.listdir(path.parent) == ["s.json"]           # no temp file left behind
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}   # the old file is intact


def test_write_json_cleans_up_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "d" / "s.json"
    config.write_json(str(path), {"a": 1})
    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        config.write_json(str(path), {"a": 2})
    assert os.listdir(path.parent) == ["s.json"]
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}


def test_settings_set_keeps_memory_and_the_last_good_file(tmp_path, monkeypatch):
    from castlib.app import Settings
    path = tmp_path / "cfg" / "settings.json"
    s = Settings(str(path))                                # the explicit path keeps working
    s.set("interval", 5)
    assert json.loads(path.read_text(encoding="utf-8"))["interval"] == 5
    monkeypatch.setattr(os, "replace", _boom)
    s.set("interval", 9)                                   # OSError is swallowed, as before
    assert s.get("interval") == 9
    assert json.loads(path.read_text(encoding="utf-8"))["interval"] == 5
    assert os.listdir(path.parent) == ["settings.json"]
    monkeypatch.undo()
    with pytest.raises(TypeError):                         # anything else still propagates
        s.set("tv", object())
    assert os.listdir(path.parent) == ["settings.json"]
    assert Settings(str(path)).get("interval") == 5


def test_write_private_mode(tmp_path):
    path = tmp_path / "sub" / "token"
    config.write_private(str(path), "secret")
    assert path.read_text(encoding="utf-8") == "secret"
    assert os.name != "posix" or oct(path.stat().st_mode & 0o777) == "0o600"
    config.write_private(str(path), "again")
    assert os.name != "posix" or oct(path.stat().st_mode & 0o777) == "0o600"
    assert path.read_text() == "again"
    # written beside and renamed over: a failed write leaves the old content and no temp file
    with pytest.raises(TypeError):
        config.write_private(str(path), None)
    assert path.read_text() == "again"
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_photo_tmp_dir_is_created_and_removed():
    d = config.photo_tmp_dir()
    assert os.path.isdir(d)
    assert config.photo_tmp_dir() == d
    config.remove_photo_tmp_dir()
    assert not os.path.exists(d)


def test_sweep_removes_only_dead_owners_video_dirs(tmp_path, monkeypatch):
    import subprocess
    import sys
    monkeypatch.setattr(config, "VIDEO_BASE", str(tmp_path))
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()                                                  # its pid names no process now
    dead = tmp_path / ("cast-tv-videos-%d-abc" % child.pid)
    mine = tmp_path / ("cast-tv-videos-%d-def" % os.getpid())
    legacy = tmp_path / "cast-tv-videos-12345678"                 # an older release's name: no pid to prove dead
    other = tmp_path / "unrelated-1-dir"
    for d in (dead, mine, legacy, other):
        d.mkdir()
        (d / "v.mp4").write_bytes(b"x")
    if os.name == "posix":                                        # Windows symlinks need a privilege
        os.symlink(str(other), str(tmp_path / ("cast-tv-videos-%d-lnk" % child.pid)))
    assert config.sweep_stale_video_dirs() == [str(dead)]
    assert not dead.exists() and mine.exists() and legacy.exists() and (other / "v.mp4").exists()
    assert os.path.basename(config.video_tmp_dir()).startswith("cast-tv-videos-%d-" % os.getpid())
    config.remove_video_tmp_dir()


def test_paths_per_platform(monkeypatch, tmp_path):
    import platformdirs.windows
    # Linux: the directories cast-tv used before platformdirs, so nothing migrates
    home = str(tmp_path / "home")
    for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", home)
    monkeypatch.setenv("USERPROFILE", home)                   # what expanduser reads on Windows
    cfg, cache = config.platform_dirs("linux")
    assert os.path.normpath(cfg) == os.path.normpath(os.path.join(home, ".config", "cast-tv"))
    assert os.path.normpath(cache) == os.path.normpath(os.path.join(home, ".cache", "cast-tv"))
    # Windows: %APPDATA%\\cast-tv and %LOCALAPPDATA%\\cast-tv\\Cache, the name not doubled
    folders = {"CSIDL_APPDATA": os.path.join(home, "AppData", "Roaming"),
               "CSIDL_LOCAL_APPDATA": os.path.join(home, "AppData", "Local")}
    monkeypatch.setattr(platformdirs.windows, "get_win_folder", lambda csidl: folders[csidl])
    cfg, cache = config.platform_dirs("win32")
    assert cfg == os.path.join(folders["CSIDL_APPDATA"], "cast-tv")
    assert cache == os.path.join(folders["CSIDL_LOCAL_APPDATA"], "cast-tv", "Cache")


def _text_mode_violations(tree):
    """``(line, call)`` for every text-mode open or subprocess call without ``encoding``."""
    import ast
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
        base = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else None
        kw = {k.arg: k.value for k in node.keywords}
        # the builtin, io.open and os.fdopen; not opener.open, webbrowser.open, Image.open, ...
        if ((isinstance(f, ast.Name) and name == "open")
                or (base == "io" and name == "open") or (base == "os" and name == "fdopen")):
            mode = kw.get("mode", node.args[1] if len(node.args) > 1 else None)
            binary = isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" in mode.value
            if not binary and "encoding" not in kw:
                bad.append((node.lineno, name))
        elif name in ("read_text", "write_text") and "encoding" not in kw:
            bad.append((node.lineno, name))
        elif base == "subprocess" and name in ("run", "Popen", "check_output", "call"):
            text = any(isinstance(kw.get(k), ast.Constant) and kw[k].value for k in ("text", "universal_newlines"))
            if text and "encoding" not in kw:
                bad.append((node.lineno, "subprocess." + name))
    return bad


def test_utf8_everywhere():
    """Every text-mode file or pipe in castlib names its encoding; never the ANSI code page."""
    import ast
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "castlib")
    found = {}
    for folder, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as fh:
                    bad = _text_mode_violations(ast.parse(fh.read(), path))
                if bad:
                    found[os.path.relpath(path, root)] = bad
    assert found == {}
    # the checker itself catches what it is there for
    sample = ast.parse("open(p)\nopen(p, 'w')\nos.fdopen(fd, 'w')\nopen(p, 'rb')\n"
                       "Path(p).read_text()\nsubprocess.run(a, text=True)\n"
                       "open(p, encoding='utf-8')\nwebbrowser.open(u)\n(a or b).open(r)\n")
    assert [line for line, _ in _text_mode_violations(sample)] == [1, 2, 3, 5, 6]


class _FakeKernel32:
    """Enough of kernel32 for ``_alive_windows``: OpenProcess, GetExitCodeProcess, CloseHandle."""

    def __init__(self, handle, error=0, exit_code=259):
        self.handle, self.error, self.exit_code, self.closed = handle, error, exit_code, []

    def OpenProcess(self, access, inherit, pid):
        return self.handle

    def last_error(self):
        return self.error

    def GetExitCodeProcess(self, handle, ref):
        ref._obj.value = self.exit_code
        return 1

    def CloseHandle(self, handle):
        self.closed.append(handle)


def test_windows_liveness_without_os_kill():
    def alive(k32):
        return config._alive_windows(4242, k32, k32.last_error)
    assert alive(_FakeKernel32(0, error=87)) is False                           # no such process
    assert alive(_FakeKernel32(0, error=5)) is True                             # someone else's
    running = _FakeKernel32(77, exit_code=259)
    assert alive(running) is True and running.closed == [77]
    ended = _FakeKernel32(78, exit_code=0)                                     # exited, handle still held elsewhere
    assert alive(ended) is False and ended.closed == [78]
