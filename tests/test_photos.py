import io
import os
import signal
import subprocess
import sys
import threading
import time

import pytest
from PIL import Image

from castlib import config, photos
from castlib.errors import NotMedia
from castlib.items import MediaItem
from castlib.photos import Prepared, _Cache
from tests.conftest import request
from tests.fixtures import make


@pytest.fixture
def fixtures(tmp_path):
    return make.write_all(str(tmp_path / "fx"))


@pytest.fixture(autouse=True)
def fresh_photo_state(monkeypatch):
    monkeypatch.setattr(photos, "cache", _Cache())
    monkeypatch.setattr(photos, "_pending", {})
    monkeypatch.setattr(photos, "_active_peak", 0)
    yield
    config.remove_photo_tmp_dir()


def _photo(path, mime=None):
    ext = os.path.splitext(path)[1].lower()
    from castlib.media import MIME
    return MediaItem(kind="photo", title=os.path.basename(path), mime=mime or MIME[ext],
                     source="local", source_id=path, path=path, size=os.path.getsize(path))


def test_heic_becomes_jpeg(fixtures):
    item = _photo(fixtures["plain.heic"])
    prep = photos.prepare(item)
    assert prep.mime == "image/jpeg"
    assert prep.profile == "JPEG_SM"
    assert (prep.width, prep.height) == (64, 48)
    with open(prep.path, "rb") as fh:
        data = fh.read()
    assert data[:3] == b"\xff\xd8\xff"
    assert prep.size == len(data) == os.path.getsize(prep.path)
    assert prep.path.startswith(config.photo_tmp_dir())


def test_exif_transpose(fixtures):
    plain = photos.prepare(_photo(fixtures["plain.jpg"]))
    oriented = photos.prepare(_photo(fixtures["oriented.jpg"]))
    assert (plain.width, plain.height) == (64, 48)
    assert (oriented.width, oriented.height) == (48, 64)      # rotated upright
    im = Image.open(oriented.path)
    assert im.size == (48, 64)
    assert int(im.getexif().get(0x0112, 1) or 1) == 1
    # the plain JPEG is stored as fetched, byte for byte
    with open(fixtures["plain.jpg"], "rb") as a, open(plain.path, "rb") as b:
        assert a.read() == b.read()


def test_png_and_webp(fixtures):
    png = photos.prepare(_photo(fixtures["plain.png"]))
    assert png.mime == "image/png" and png.profile == "PNG_LRG"
    webp = photos.prepare(_photo(fixtures["plain.webp"]))
    assert webp.mime == "image/jpeg"


def test_oversize_is_downscaled(tmp_path, monkeypatch):
    monkeypatch.setattr(photos, "PHOTO_MAX", 100)
    path = tmp_path / "big.jpg"
    path.write_bytes(make.jpeg(400, 200))
    prep = photos.prepare(_photo(str(path)))
    assert (prep.width, prep.height) == (100, 50)
    assert prep.profile == "JPEG_SM"


def test_gif_is_refused(fixtures):
    with pytest.raises(NotMedia):
        photos.prepare(_photo(fixtures["plain.gif"], mime="image/gif"))


def test_garbage_is_refused(tmp_path):
    path = tmp_path / "x.jpg"
    path.write_bytes(b"not a photo at all")
    with pytest.raises(NotMedia):
        photos.prepare(_photo(str(path)))


def test_prepared_keeps_source_fields(fixtures):
    item = _photo(fixtures["plain.heic"])
    source_size = item.size
    prep = photos.prepare(item)
    assert item.mime == "image/heic"
    assert item.size == source_size
    assert item.width is None and item.height is None
    assert item.prepared is prep
    assert prep.mime == "image/jpeg" and prep.size != source_size


def test_head_get_agree_after_conversion(server, fixtures):
    srv, base = server
    item = _photo(fixtures["plain.heic"])
    photos.prepare(item)
    srv.registry.add(item)
    url = "/m/%s/%s" % (srv.media_token, item.id)
    s1, h1, b1, conn = request(base, "HEAD", url)
    s2, h2, b2, _ = request(base, "GET", url, conn=conn)
    assert (s1, s2) == (200, 200)
    assert h1["Content-Length"] == h2["Content-Length"] == str(item.prepared.size)
    assert h2["Content-Type"] == "image/jpeg"
    assert b2[:3] == b"\xff\xd8\xff" and len(b2) == item.prepared.size
    assert h2["transferMode.dlna.org"] == "Interactive"
    assert h2["contentFeatures.dlna.org"].startswith("DLNA.ORG_PN=JPEG_SM;DLNA.ORG_OP=00")
    s3, h3, b3, _ = request(base, "GET", url, {"Range": "bytes=0-2"}, conn=conn)
    assert s3 == 206 and b3 == b"\xff\xd8\xff"


def test_unprepared_photo_is_404(server, fixtures):
    srv, base = server
    item = srv.registry.add(_photo(fixtures["plain.jpg"]))
    status, _, _, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id))
    assert status == 404


def test_cache_hits_and_version_changes(fixtures):
    item = _photo(fixtures["plain.heic"])
    first = photos.prepare(item)
    again = photos.prepare(_photo(fixtures["plain.heic"]))
    assert again.path == first.path
    assert len(photos.cache) == 1
    # touching the file changes mtime: a new version, a new conversion
    time.sleep(0.01)
    with open(fixtures["plain.heic"], "ab") as fh:
        fh.write(b"\0")
    third = photos.prepare(_photo(fixtures["plain.heic"]))
    assert third.path != first.path
    assert len(photos.cache) == 2


def test_cache_evicts_by_bytes(tmp_path):
    cache = _Cache(max_bytes=250, max_entries=100)
    preps = []
    for n in range(4):
        path = tmp_path / ("p%d.jpg" % n)
        path.write_bytes(b"x" * 100)
        preps.append(Prepared(str(path), "image/jpeg", 100, 1, 1, "JPEG_SM"))
        cache.put(("local", str(path), ""), preps[-1])
    assert len(cache) == 2 and cache.bytes == 200
    assert not os.path.exists(preps[0].path) and not os.path.exists(preps[1].path)
    assert os.path.exists(preps[2].path) and os.path.exists(preps[3].path)
    small = _Cache(max_bytes=1000, max_entries=1)
    for prep in preps[2:]:
        small.put(("local", prep.path, ""), prep)
    assert len(small) == 1 and not os.path.exists(preps[2].path)


def test_concurrency_bounded(tmp_path, monkeypatch):
    real = photos._convert

    def slow(item, data):
        time.sleep(0.15)
        return real(item, data)

    monkeypatch.setattr(photos, "_convert", slow)
    items = []
    for n in range(6):
        path = tmp_path / ("c%d.jpg" % n)
        path.write_bytes(make.jpeg(8 + n, 8))
        items.append(_photo(str(path)))
    threads = [threading.Thread(target=photos.prepare, args=(i,)) for i in items]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(i.prepared is not None for i in items)
    assert photos.peak_concurrency() <= 2


def test_prefetch_does_not_block(tmp_path, monkeypatch):
    real = photos._convert
    started = threading.Event()

    def slow(item, data):
        started.set()
        time.sleep(0.2)
        return real(item, data)

    monkeypatch.setattr(photos, "_convert", slow)
    path = tmp_path / "pf.jpg"
    path.write_bytes(make.jpeg())
    item = _photo(str(path))
    t0 = time.time()
    photos.prefetch([item])
    assert time.time() - t0 < 0.1
    assert started.wait(2)
    prep = photos.prepare(item)          # joins the pending conversion
    assert prep.width == 64


def test_tmp_dir_removed_at_exit():
    code = ("import sys, time; from castlib import config; "
            "print(config.photo_tmp_dir(), flush=True); time.sleep(30)")
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE,
                            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = proc.stdout.readline().decode().strip()
    assert os.path.isdir(path)
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=10)
    assert not os.path.exists(path)


def test_conversion_failure_sends_no_soap(tmp_path, monkeypatch, capsys):
    from castlib import cli
    bad = tmp_path / "broken.jpg"
    bad.write_bytes(b"\xff\xd8 definitely not a jpeg")
    calls = []
    monkeypatch.setattr(cli, "soap", lambda *a, **kw: calls.append(a))
    monkeypatch.setattr(cli, "find_tv", lambda tv: ("127.0.0.1", "http://127.0.0.1:1/avt"))
    monkeypatch.setattr(cli, "local_ip", lambda ip: "127.0.0.1")
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    assert cli.cast(str(bad), tv="127.0.0.1", port=port) == 1
    assert calls == []
    assert "not a photo the TV can show" in capsys.readouterr().out


def test_cli_refuses_gif(tmp_path, monkeypatch, capsys):
    from castlib import cli
    path = tmp_path / "anim.gif"
    path.write_bytes(make.gif())
    monkeypatch.setattr(cli, "find_tv", lambda tv: ("127.0.0.1", "http://127.0.0.1:1/avt"))
    assert cli.cast(str(path), tv="127.0.0.1", port=0) == 1
    assert "GIF" in capsys.readouterr().out


def test_remote_photo_fetched_with_headers(server, upstream):
    from castlib.items import Upstream
    up = upstream(make.heic(), ctype="image/heic")
    item = MediaItem(kind="photo", title="cloud.heic", mime="image/heic", source="gphotos",
                     source_id="abc", version="v1",
                     resolve=lambda: Upstream(up.base + "/photo=d",
                                              headers={"Authorization": "Bearer t"}))
    prep = photos.prepare(item)
    assert prep.mime == "image/jpeg"
    assert up.requests[0]["headers"].get("Authorization") == "Bearer t"
    assert io.BytesIO(open(prep.path, "rb").read()).read(2) == b"\xff\xd8"


# ---- Phase 2 review findings (reviews/impl-review-phase-2.md)

def test_submit_with_completed_future_does_not_deadlock(tmp_path, monkeypatch):
    """F1: a worker that finishes before the callback is attached must not hang."""
    from concurrent.futures import Future
    path = tmp_path / "done.jpg"
    path.write_bytes(make.jpeg())
    item = _photo(str(path))
    ready = Prepared(str(path), "image/jpeg", path.stat().st_size, 64, 48, "JPEG_SM")

    def completed(fn, *a):
        fut = Future()
        fut.set_result(ready)
        return fut

    monkeypatch.setattr(photos._pool, "submit", completed)
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("prep", photos.prepare(item)))
    t.start()
    t.join(2)
    assert not t.is_alive(), "_submit deadlocked on a completed future"
    assert result["prep"] is ready
    assert photos._pending == {}
    assert photos.cache.get(photos.cache_key(item)) is ready


def test_registered_photo_survives_cache_pressure(server, tmp_path, monkeypatch):
    """F2: a file the registry still serves is never deleted by cache eviction."""
    from castlib.items import Registry
    monkeypatch.setattr(photos, "cache", _Cache(max_bytes=10 ** 9, max_entries=1))
    reg = Registry()
    photos.attach(reg)
    paths = []
    for n in range(2):
        p = tmp_path / ("r%d.heic" % n)
        p.write_bytes(make.heic(32 + n, 32))
        paths.append(p)
    a = _photo(str(paths[0]))
    photos.prepare(a)
    reg.add(a)
    b = _photo(str(paths[1]))
    photos.prepare(b)                 # pushes the 1-entry cache over its limit
    assert os.path.exists(a.prepared.path), "A is registered; its file must survive"
    assert os.path.exists(b.prepared.path)
    assert len(photos.cache) == 2      # both retained beyond the bound
    reg.remove(a.id)                   # the registry releases A's pin
    assert not os.path.exists(a.prepared.path)
    assert os.path.exists(b.prepared.path)
    # eviction releases too
    reg.add(b)
    reg.retire(b.id)
    b.last_request = time.time() - 120
    reg.evict(60)
    assert not photos.cache.pinned(photos.cache_key(b))


def test_prepare_twice_pins_once(tmp_path):
    path = tmp_path / "twice.jpg"
    path.write_bytes(make.jpeg())
    item = _photo(str(path))
    first = photos.prepare(item)
    assert photos.prepare(item) is first
    photos.release(item)
    assert not photos.cache.pinned(photos.cache_key(item))


def test_decompression_bomb_is_cast_error(tmp_path, monkeypatch):
    """F3: Pillow's pixel limit surfaces as NotMedia, not a traceback."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)     # 64x48 = 3072 > 2x limit
    path = tmp_path / "bomb.jpg"
    path.write_bytes(make.jpeg())
    with pytest.raises(NotMedia) as info:
        photos.prepare(_photo(str(path)))
    assert info.value.code == "photo_too_many_pixels"


def test_write_failure_is_cast_error_without_partial_file(tmp_path, monkeypatch):
    """F3: a temp-file failure is a ConfigError and leaves nothing behind."""
    from castlib.errors import CastError, ConfigError

    def refuse(*a, **kw):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(photos.tempfile, "mkstemp", refuse)
    path = tmp_path / "nospace.jpg"
    path.write_bytes(make.jpeg())
    with pytest.raises(ConfigError) as info:
        photos.prepare(_photo(str(path)))
    assert isinstance(info.value, CastError)
    assert os.listdir(config.photo_tmp_dir()) == []


def test_bomb_sends_no_soap(tmp_path, monkeypatch, capsys):
    from castlib import cli
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    path = tmp_path / "bomb.jpg"
    path.write_bytes(make.jpeg())
    calls = []
    monkeypatch.setattr(cli, "soap", lambda *a, **kw: calls.append(a))
    monkeypatch.setattr(cli, "find_tv", lambda tv: ("127.0.0.1", "http://127.0.0.1:1/avt"))
    monkeypatch.setattr(cli, "local_ip", lambda ip: "127.0.0.1")
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    assert cli.cast(str(path), tv="127.0.0.1", port=port) == 1
    assert calls == []
    assert "more pixels" in capsys.readouterr().out


def test_oriented_png_becomes_jpeg(tmp_path):
    """F4: PNG is kept only untouched; a transposed one is re-encoded to JPEG."""
    im = Image.new("RGB", (64, 48), (10, 200, 10))
    exif = Image.Exif()
    exif[0x0112] = 6
    path = tmp_path / "oriented.png"
    im.save(path, format="PNG", exif=exif.tobytes())
    prep = photos.prepare(_photo(str(path)))
    assert prep.mime == "image/jpeg"
    assert (prep.width, prep.height) == (48, 64)
    assert prep.profile == "JPEG_SM"
