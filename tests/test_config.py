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
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    config.write_private(str(path), "again")
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_photo_tmp_dir_is_created_and_removed():
    d = config.photo_tmp_dir()
    assert os.path.isdir(d)
    assert config.photo_tmp_dir() == d
    config.remove_photo_tmp_dir()
    assert not os.path.exists(d)
