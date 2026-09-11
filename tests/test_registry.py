import threading
import time

from castlib.items import MediaItem, Registry
from tests.conftest import request


def _item(kind="video", parent=None):
    return MediaItem(kind=kind, title="t", mime="video/mp4", source="local",
                     source_id="x", path="/nonexistent", parent=parent)


def test_add_is_atomic_and_unique():
    reg = Registry()
    ids, lock = [], threading.Lock()

    def worker():
        for _ in range(50):
            item = reg.add(_item())
            with lock:
                ids.append(item.id)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ids) == 400
    assert len(set(ids)) == 400
    assert all(reg.get(i) is not None for i in ids)


def test_evict_after_idle():
    reg = Registry()
    old = reg.add(_item())
    fresh = reg.add(_item())
    reg.retire(old.id)
    reg.retire(fresh.id)
    old.last_request = time.time() - 120
    gone = reg.evict(60)
    assert [i.id for i in gone] == [old.id]
    assert reg.get(old.id) is None
    assert reg.get(fresh.id) is fresh


def test_active_item_survives_idle():
    reg = Registry()
    item = reg.add(_item())
    item.last_request = time.time() - 24 * 3600
    assert reg.evict(60) == []
    assert reg.get(item.id) is item


def test_in_flight_blocks_eviction():
    reg = Registry()
    item = reg.add(_item())
    reg.retire(item.id)
    item.last_request = time.time() - 120
    reg.begin(item.id)
    assert reg.evict(60) == []
    reg.end(item.id)
    assert reg.evict(60) == [item]


def test_readd_clears_retired():
    reg = Registry()
    item = reg.add(_item())
    reg.retire(item.id)
    reg.remove(item.id)
    reg.add(item)
    assert item.retired_at is None
    assert reg.evict(0.0) == []


def test_revive_clears_retired_for_item_and_subtitle():
    reg = Registry()
    video = reg.add(_item())
    sub = reg.add(_item("subtitle", parent=video.id))
    reg.retire(video.id)
    assert video.retired_at is not None and sub.retired_at is not None
    reg.revive(video.id)
    assert video.retired_at is None and sub.retired_at is None
    assert reg.evict(0.0) == []
    reg.revive("missing")                                  # unknown ids are ignored


def test_retire_video_retires_subtitle():
    reg = Registry()
    sub = reg.add(_item(kind="subtitle"))
    video = reg.add(_item())
    sub.parent = video.id
    reg.retire(video.id)
    assert video.retired_at is not None
    assert sub.retired_at is not None


def test_touch_counts_requests():
    reg = Registry()
    item = reg.add(_item())
    before = item.last_request
    time.sleep(0.01)
    reg.touch(item.id)
    assert item.requests == 1
    assert item.last_request > before


def test_second_item_does_not_replace_first(server, local_file):
    srv, base = server
    first, data1 = local_file(srv, "a.mp4", bytes([1]) * 300)
    second, data2 = local_file(srv, "b.mp4", bytes([2]) * 400)
    s1, _, body1, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, first.id))
    s2, _, body2, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, second.id))
    assert (s1, body1) == (200, data1)
    assert (s2, body2) == (200, data2)
    assert srv.registry.get(first.id) is first
    assert srv.registry.get(second.id) is second
