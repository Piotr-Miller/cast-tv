"""The cast supervisor and the slideshow engine, against a scripted ``soap()``."""
import threading
import time

from castlib.platform import firewall_hint
from castlib.sources.local import item_for_path
from tests.conftest import request, wait_for
from tests.fixtures import make


def _video(tmp_path, name="clip.mp4"):
    p = tmp_path / name
    p.write_bytes(bytes(range(256)) * 2)
    return item_for_path(str(p))


def _photo(tmp_path, name="p.jpg"):
    p = tmp_path / name
    p.write_bytes(make.jpeg(64, 48))
    return item_for_path(str(p))


def _media_path(app, item):
    return "/m/%s/%s" % (app.server.media_token, item.id)


# ------------------------------------------------------------------ Cast
def test_started_latch_and_budget(app, tmp_path):
    tv = app.tv_fake
    tv.video_script = ["TRANSITIONING", "PAUSED_PLAYBACK", "PLAYING", "STOPPED"]
    c = app.cast(_video(tmp_path, "a.mp4"))
    assert c.done.wait(5)
    assert c.state == "stopped" and c.started
    assert c.position == "0:00:01"            # as reported, never zero-padded by us

    # a TV that transitions and then refuses: failed after the budget, not before
    tv.video_script = ["TRANSITIONING", "STOPPED"]
    item = _video(tmp_path, "b.mp4")
    c2 = app.cast(item)
    assert c2.sent.wait(5)
    status, _, _, _ = request(app.base_url, "HEAD", _media_path(app, item))
    assert status == 200                      # the TV did fetch: not the firewall case
    assert not c2.done.wait(0.15)             # still inside the 0.3 s budget
    assert c2.done.wait(5)
    assert c2.state == "failed"
    assert c2.reason.code == "tv_never_started"
    assert not c2.started


def test_zero_requests_is_firewall_diagnosis(app, tmp_path):
    app.tv_fake.video_script = ["STOPPED"]
    c = app.cast(_video(tmp_path))
    assert c.done.wait(5)
    assert c.state == "failed"
    assert c.reason.code == "tv_fetched_nothing"
    assert firewall_hint(app.server.port) in c.reason.hint
    assert app.errors.list()[-1]["code"] == "tv_fetched_nothing"
    assert c.item.retired_at is not None


def test_replace_keeps_old_item(app, tmp_path):
    tv = app.tv_fake
    tv.video_script = ["PLAYING"]
    a = app.cast(_video(tmp_path, "a.mp4"))
    assert a.sent.wait(5)
    wait_for(lambda: a.state == "playing")
    b = app.cast(_video(tmp_path, "b.mp4"))
    assert b.sent.wait(5)
    wait_for(lambda: a.state == "replaced")
    assert app.current is b
    assert app.registry.get(a.item.id) is a.item          # left registered
    assert a.item.retired_at is not None                  # but retired, for later eviction
    status, _, body, _ = request(app.base_url, "GET", _media_path(app, a.item))
    assert status == 200 and len(body) == 512             # the TV can still fetch it
    assert tv.uri_ids() == [a.item.id, b.item.id]
    assert "Stop" not in tv.actions()                     # replacing never sends Stop


def test_stop_during_set_uri_is_not_undone(app, tmp_path):
    tv = app.tv_fake
    tv.video_script = ["PLAYING"]
    tv.hooks["SetAVTransportURI"] = app.stop      # lands while the TV is being addressed
    c = app.cast(_video(tmp_path))
    assert c.done.wait(5)
    assert c.state == "cancelled" and not c.promoted
    assert app.current is None and app.owner is None
    assert tv.actions() == ["SetAVTransportURI", "Stop", "Play", "Stop"]
    assert c.item.retired_at is not None


def test_stop_during_play_is_not_undone(app, tmp_path):
    tv = app.tv_fake
    tv.video_script = ["PLAYING"]
    tv.hooks["Play"] = app.stop
    c = app.cast(_video(tmp_path))
    assert c.done.wait(5)
    assert c.state == "cancelled" and not c.promoted
    assert app.current is None
    assert tv.actions() == ["SetAVTransportURI", "Play", "Stop", "Stop"]


def test_stop_just_before_promotion_is_not_undone(app, tmp_path, monkeypatch):
    tv = app.tv_fake
    tv.video_script = ["PLAYING"]
    real = app._promote

    def stop_then_promote(cast):
        app.stop()                                # the last instant before the seat is taken
        return real(cast)
    monkeypatch.setattr(app, "_promote", stop_then_promote)
    c = app.cast(_video(tmp_path))
    assert c.done.wait(5)
    assert c.state == "cancelled" and not c.promoted
    assert app.current is None
    assert tv.actions() == ["SetAVTransportURI", "Play", "Stop", "Stop"]


def test_superseded_before_promotion_sends_no_stop(app, tmp_path):
    tv = app.tv_fake
    tv.video_script = ["PLAYING"]
    later = {}
    b_item = _video(tmp_path, "b.mp4")
    tv.hooks["Play"] = lambda: later.update(b=app.cast(b_item))   # a newer owner, mid-Play
    a = app.cast(_video(tmp_path, "a.mp4"))
    assert a.done.wait(5)
    assert a.state == "cancelled" and not a.promoted
    b = later["b"]
    assert b.sent.wait(5)
    wait_for(lambda: b.state == "playing")
    assert app.current is b
    assert tv.uri_ids() == [a.item.id, b.item.id]
    assert "Stop" not in tv.actions()                     # the newer cast replaces on the TV


def test_stale_task_releases_prepared_photo(app, tmp_path, monkeypatch):
    from castlib import photos
    real = photos.prepare
    gate = threading.Event()

    def held(item):
        prep = real(item)
        gate.wait(5)                              # the second cast is accepted meanwhile
        return prep
    monkeypatch.setattr(photos, "prepare", held)
    a = app.cast(_photo(tmp_path))
    b = app.cast(_video(tmp_path))
    gate.set()
    assert a.done.wait(5)
    assert a.state == "cancelled" and not a.item.id
    assert a.item.prepared is not None
    assert not photos.cache.pinned(photos.cache_key(a.item))   # nothing else will unpin it
    assert b.sent.wait(5)
    monkeypatch.setattr(photos, "prepare", real)
    app.tv = None                                 # and the no-TV branch
    c = app.cast(_photo(tmp_path, "q.jpg"))
    assert c.done.wait(5)
    assert c.state == "failed" and c.reason.code == "no_tv"
    assert not photos.cache.pinned(photos.cache_key(c.item))


def test_stale_task_skipped_after_prepare(app, tmp_path, monkeypatch):
    from castlib import photos
    real = photos.prepare

    def slow(item):
        time.sleep(0.3)
        return real(item)
    monkeypatch.setattr(photos, "prepare", slow)
    a = app.cast(_photo(tmp_path))
    time.sleep(0.05)
    b = app.cast(_video(tmp_path))            # accepted second, wins
    assert a.done.wait(5)
    assert a.state == "cancelled"
    assert b.sent.wait(5)
    assert app.tv_fake.uri_ids() == [b.item.id]           # nothing was sent for a
    assert not a.item.id                                  # never registered either


def test_unreachable_tv_fails_the_cast_and_flags_the_header(app, tmp_path):
    tv = app.tv_fake
    tv.video_script = ["PLAYING"]
    c = app.cast(_video(tmp_path))
    assert c.sent.wait(5)
    tv.fail = True
    assert c.done.wait(5)
    assert c.state == "failed" and c.reason.code == "tv_unreachable"
    assert app.tv["state"] == "unreachable"


def test_stop_sends_stop_once_and_retires(app, tmp_path):
    tv = app.tv_fake
    tv.video_script = ["PLAYING"]
    c = app.cast(_video(tmp_path))
    assert c.sent.wait(5)
    app.stop()
    assert c.done.wait(5)
    assert c.state == "stopped"
    assert tv.actions().count("Stop") == 1
    assert c.item.retired_at is not None


def test_play_refused_with_701_is_fine_when_already_playing(app, tmp_path):
    tv = app.tv_fake
    tv.faults = {"Play": "701"}               # the Samsung, once it fetched the still itself
    c = app.cast(_photo(tmp_path))
    assert c.sent.wait(5)
    wait_for(lambda: c.state == "playing")
    assert tv.actions()[:3] == ["SetAVTransportURI", "Play", "GetTransportInfo"]

    tv.video_script = ["STOPPED"]             # but a 701 on something not playing is a refusal
    c2 = app.cast(_video(tmp_path))
    assert c2.done.wait(5)
    assert c2.state == "failed" and c2.reason.code == "tv_rejected"
    assert "UPnP 701: Transition not available" in c2.reason.message


def test_716_on_set_uri_with_no_request_is_the_firewall_diagnosis(app, tmp_path):
    tv = app.tv_fake
    tv.faults = {"SetAVTransportURI": "716"}  # the Samsung probes the address and cannot reach it
    c = app.cast(_video(tmp_path))
    assert c.done.wait(5)
    assert c.state == "failed" and c.reason.code == "tv_fetched_nothing"
    assert firewall_hint(app.server.port) in c.reason.hint
    # the same fault after the TV did fetch is a plain refusal
    item = _video(tmp_path, "b.mp4")
    app.registry.add(item)
    app.registry.touch(item.id)
    c2 = app.cast(item)
    assert c2.done.wait(5)
    assert c2.reason.code == "tv_rejected" and "UPnP 716" in c2.reason.message


# ------------------------------------------------------------------ Show
def test_show_order_is_selection_order(app, tmp_path):
    items = [_photo(tmp_path, "p%d.jpg" % i) for i in range(3)]
    sh = app.show(items, interval=2)
    sh.interval = 0.1                          # the API bound is 2 s; the engine takes any float
    assert sh.done.wait(10)
    assert sh.state == "finished"
    assert app.tv_fake.uri_ids() == [i.id for i in items]
    actions = app.tv_fake.actions()                      # a finished show clears the screen
    last_set = len(actions) - 1 - actions[::-1].index("SetAVTransportURI")
    assert "Stop" in actions[last_set:]


def test_show_waits_for_video_end(app, tmp_path):
    tv = app.tv_fake
    tv.video_script = ["TRANSITIONING"] * 5 + ["PLAYING"] * 10 + ["STOPPED"]
    items = [_video(tmp_path), _photo(tmp_path)]
    sh = app.show(items, interval=2)
    sh.interval = 0.1
    assert sh.done.wait(10)
    sets = tv.times("SetAVTransportURI")
    assert len(sets) == 2
    assert sets[1][0] - sets[0][1] >= 15 * 0.02           # not before the video reached STOPPED
    assert tv.uri_ids() == [i.id for i in items]


def test_show_skips_failed_item(app, tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not a photo at all")
    items = [_photo(tmp_path, "a.jpg"), item_for_path(str(bad)), _photo(tmp_path, "c.jpg")]
    sh = app.show(items, interval=2)
    sh.interval = 0.1
    assert sh.done.wait(10)
    assert sh.state == "finished" and sh.skipped == 1
    assert app.tv_fake.uri_ids() == [items[0].id, items[2].id]
    assert any(e["code"] == "photo_undecodable" for e in app.errors.list())


def test_show_prefetches_next_photos(app, tmp_path, monkeypatch):
    from castlib import photos
    calls = []
    monkeypatch.setattr(photos, "prefetch", lambda items: calls.append(list(items)))
    items = [_photo(tmp_path, "p%d.jpg" % i) for i in range(4)]
    sh = app.show(items, interval=2)
    sh.interval = 0.1
    assert sh.done.wait(10)
    assert calls[0] == [items[1], items[2]]
    assert calls[1] == [items[2], items[3]]
    assert calls[2] == [items[3]]


def test_manual_cast_cancels_show(app, tmp_path):
    items = [_photo(tmp_path, "p%d.jpg" % i) for i in range(3)]
    sh = app.show(items, interval=2)
    wait_for(lambda: sh.current is not None and sh.current.sent.is_set())
    v = app.cast(_video(tmp_path))
    assert sh.done.wait(5)
    assert sh.state == "cancelled"
    assert v.sent.wait(5)
    time.sleep(0.2)
    assert app.tv_fake.uri_ids() == [items[0].id, v.item.id]   # the show cast nothing further
    assert app.current is v
    assert not app.stay_awake.active or app.current is v


def test_new_show_cancels_show(app, tmp_path):
    first = app.show([_photo(tmp_path, "a.jpg"), _photo(tmp_path, "b.jpg")], interval=2)
    wait_for(lambda: first.current is not None and first.current.sent.is_set())
    second = app.show([_photo(tmp_path, "c.jpg")], interval=2)
    assert first.done.wait(5)
    assert first.state == "cancelled"
    wait_for(lambda: second.current is not None and second.current.sent.is_set())
    assert app.show_now is second
    app.stop()
    assert second.done.wait(5)


def test_show_wait_ends_on_replaced(app, tmp_path):
    app.tv_fake.video_script = ["PLAYING"]                # a video that never ends
    sh = app.show([_video(tmp_path, "long.mp4"), _photo(tmp_path)], interval=2)
    wait_for(lambda: sh.current is not None and sh.current.sent.is_set())
    t0 = time.monotonic()
    app.cast(_video(tmp_path, "other.mp4"))
    assert sh.done.wait(3)
    assert time.monotonic() - t0 < 1.0
    assert sh.state == "cancelled"


def test_single_photo_show_holds_until_stop(app, tmp_path):
    sh = app.show([_photo(tmp_path)], interval=2)
    sh.interval = 0.05
    wait_for(lambda: sh.current is not None and sh.current.sent.is_set())
    time.sleep(0.4)
    assert not sh.done.is_set()
    assert len(app.tv_fake.uris) == 1
    assert sh.remaining() is None
    app.stop()
    assert sh.done.wait(5)
    assert sh.state == "stopped"
    assert "Stop" in app.tv_fake.actions()


def test_interval_counts_from_play(app, tmp_path):
    tv = app.tv_fake
    tv.play_delay = 0.3                                   # the TV takes its time answering Play
    sh = app.show([_photo(tmp_path, "a.jpg"), _photo(tmp_path, "b.jpg")], interval=2)
    sh.interval = 0.5
    assert sh.done.wait(10)
    sets = tv.times("SetAVTransportURI")
    plays = tv.times("Play")
    assert len(sets) == 2 and len(plays) == 2
    assert sets[1][0] - plays[0][1] >= 0.5                # interval from the moment Play returned
    assert sets[1][0] - sets[0][0] >= 0.8                 # so 0.3 + 0.5, not 0.5


def test_show_pause_freezes_the_interval(app, tmp_path):
    sh = app.show([_photo(tmp_path, "a.jpg"), _photo(tmp_path, "b.jpg")], interval=2)
    sh.interval = 0.3
    wait_for(lambda: sh.current is not None and sh.current.sent.is_set())
    sh.pause()
    assert sh.state == "paused"
    time.sleep(0.5)
    assert len(app.tv_fake.uris) == 1
    sh.resume()
    assert sh.done.wait(10)
    assert len(app.tv_fake.uris) == 2


def test_prev_item_is_not_evictable(app, tmp_path):
    from castlib import photos
    items = [_photo(tmp_path, "p%d.jpg" % i) for i in range(2)]
    sh = app.show(items, interval=2)
    wait_for(lambda: sh.current is not None and sh.current.sent.is_set())
    sh.next()
    wait_for(lambda: sh.index == 1 and sh.current.sent.is_set())
    assert items[0].retired_at is not None                # replaced, so retired
    sh.prev()
    wait_for(lambda: len(app.tv_fake.uris) == 3 and sh.current.promoted)
    assert sh.current.item is items[0]
    assert items[0].retired_at is None                    # playing again: revived
    gone = app.registry.evict(0.0)
    assert items[0] not in gone and items[1] in gone
    assert app.registry.get(items[0].id) is items[0]
    assert photos.cache.pinned(photos.cache_key(items[0]))
    app.stop()
    assert sh.done.wait(5)


def test_prev_after_eviction_re_registers_and_pins(app, tmp_path):
    from castlib import photos
    items = [_photo(tmp_path, "p%d.jpg" % i) for i in range(2)]
    sh = app.show(items, interval=2)
    wait_for(lambda: sh.current is not None and sh.current.sent.is_set())
    sh.next()
    wait_for(lambda: sh.index == 1 and sh.current.sent.is_set())
    old_id = items[0].id
    assert items[0] in app.registry.evict(0.0)             # idle long enough, gone
    assert not photos.cache.pinned(photos.cache_key(items[0]))
    sh.prev()
    wait_for(lambda: len(app.tv_fake.uris) == 3 and sh.current.promoted)
    assert items[0].id != old_id                           # re-added under a fresh id
    assert app.registry.get(items[0].id) is items[0]
    assert items[0].retired_at is None
    assert photos.cache.pinned(photos.cache_key(items[0]))   # pinned again for the TV
    app.stop()
    assert sh.done.wait(5)


def test_show_next_and_prev(app, tmp_path):
    items = [_photo(tmp_path, "p%d.jpg" % i) for i in range(3)]
    sh = app.show(items, interval=2)
    wait_for(lambda: sh.current is not None and sh.current.sent.is_set())
    sh.next()
    wait_for(lambda: sh.index == 1 and sh.current.sent.is_set())
    sh.prev()
    wait_for(lambda: len(app.tv_fake.uris) == 3)
    assert app.tv_fake.uri_ids()[-1] == items[0].id
    assert sh.as_dict()["index"] == 0
    app.stop()
    assert sh.done.wait(5)
