from castlib.items import MediaItem, Upstream
from tests.conftest import request

BODY = bytes(range(256)) * 4     # 1024 bytes


def _relayed(srv, resolver):
    return srv.registry.add(MediaItem(kind="video", title="clip", mime="video/mp4",
                                      source="link", source_id="s", resolve=resolver))


def test_206_synthesised_when_upstream_ignores_range(server, upstream):
    srv, base = server
    up = upstream(BODY, honour_range=False)
    item = _relayed(srv, lambda: Upstream(up.base + "/clip"))
    status, headers, body, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id),
                                       {"Range": "bytes=600-"})
    assert status == 206
    assert headers["Content-Range"] == "bytes 600-1023/1024"
    assert headers["Content-Length"] == "424"
    assert body == BODY[600:]
    assert up.requests[-1]["headers"].get("Range") == "bytes=600-"


def test_honoured_range_passes_through(server, upstream):
    srv, base = server
    up = upstream(BODY, honour_range=True)
    item = _relayed(srv, lambda: Upstream(up.base + "/clip"))
    status, headers, body, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id),
                                       {"Range": "bytes=10-19"})
    assert status == 206
    assert body == BODY[10:20]
    assert headers["Content-Range"] == "bytes 10-19/1024"


def test_reresolve_once(server, upstream):
    srv, base = server
    up = upstream(BODY, statuses={"/old": 403})
    calls = []

    def resolver():
        calls.append(1)
        return Upstream(up.base + ("/old" if len(calls) == 1 else "/new"))

    item = _relayed(srv, resolver)
    status, _, body, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id))
    assert status == 200
    assert body == BODY
    assert len(calls) == 2
    assert [r["path"] for r in up.requests] == ["/old", "/new"]


def test_reresolve_gives_up_after_one_retry(server, upstream):
    srv, base = server
    up = upstream(BODY, statuses={"/dead": 404})
    calls = []

    def resolver():
        calls.append(1)
        return Upstream(up.base + "/dead")

    item = _relayed(srv, resolver)
    status, _, _, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id))
    assert status == 502
    assert len(calls) == 2


def test_bearer_header_forwarded(server, upstream):
    srv, base = server
    up = upstream(BODY)
    item = _relayed(srv, lambda: Upstream(up.base + "/clip",
                                          headers={"Authorization": "Bearer abc"}))
    for rng in ("bytes=0-1", "bytes=500-"):
        status, _, _, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id),
                                  {"Range": rng})
        assert status == 206
    assert all(r["headers"].get("Authorization") == "Bearer abc" for r in up.requests)
    assert len(up.requests) == 2


def test_generic_upstream_type_is_overridden_by_item_mime(server, upstream):
    srv, base = server
    up = upstream(BODY, ctype="binary/octet-stream")
    item = _relayed(srv, lambda: Upstream(up.base + "/clip"))
    status, headers, _, _ = request(base, "HEAD", "/m/%s/%s" % (srv.media_token, item.id))
    assert status == 200
    assert headers["Content-Type"] == "video/mp4"
    assert headers["transferMode.dlna.org"] == "Streaming"


def test_cookie_opener_is_used_for_upstream(server, upstream, tmp_path):
    import http.cookiejar
    import urllib.request
    srv, base = server
    up = upstream(BODY)
    jar_file = tmp_path / "cookies.txt"
    jar_file.write_text("# Netscape HTTP Cookie File\n"
                        "127.0.0.1\tFALSE\t/\tFALSE\t2000000000\tsession\tabc123\n", encoding="utf-8")
    jar = http.cookiejar.MozillaCookieJar()
    jar.load(str(jar_file), ignore_discard=True, ignore_expires=True)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    item = _relayed(srv, lambda: Upstream(up.base + "/clip", opener=opener))
    status, _, body, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id))
    assert status == 200
    assert body == BODY
    assert "session=abc123" in up.requests[0]["headers"].get("Cookie", "")
