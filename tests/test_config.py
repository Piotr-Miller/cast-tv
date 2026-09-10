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
