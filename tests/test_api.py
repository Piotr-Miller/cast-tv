"""The JSON routes, end to end over the in-process server."""
import http.client
import json
import os
import urllib.parse

from castlib.api import MAX_SHOW_ITEMS
from castlib.errors import CastError
from castlib.items import Upstream
from castlib.sources.base import Listing
from castlib.sources.local import item_for_path
from tests.conftest import request, wait_for
from tests.fixtures import make


def _json(base, method, path, body=None, headers=None):
    host = base.split("://", 1)[1]
    conn = http.client.HTTPConnection(host, timeout=5)
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
        hdrs["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, resp.headers, (json.loads(raw) if raw else None)


def test_status_shape(app):
    status, headers, d = _json(app.base_url, "GET", "/api/status")
    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert d["app"] == "cast-tv" and d["version"]
    assert d["tv"] == {"ip": "127.0.0.1", "name": "Fake TV", "state": "ready"}
    assert d["tvs"] == [] and d["cast"] is None and d["show"] is None
    assert d["sources"] == {} and d["session"] == []
    assert isinstance(d["addresses"], list) and d["errors"] == 0 and d["errors_seq"] == 0
    assert d["settings"]["interval"] == 8
    assert "firewall_hint" in d


def test_settings_interval_bounds(app, tmp_path):
    for bad in (1, 601, "8", True, None, -3):
        status, _, d = _json(app.base_url, "POST", "/api/settings", {"interval": bad})
        assert status == 400, bad
        assert d["error"]["code"] == "bad_interval"
    status, _, d = _json(app.base_url, "POST", "/api/settings", {"interval": 2})
    assert status == 200 and d["settings"]["interval"] == 2
    status, _, d = _json(app.base_url, "POST", "/api/settings", {"interval": 600})
    assert status == 200 and d["settings"]["interval"] == 600
    status, _, d = _json(app.base_url, "GET", "/api/settings")
    assert d["settings"]["interval"] == 600
    with open(os.path.join(str(tmp_path / "config"), "settings.json"), encoding="utf-8") as fh:
        assert json.load(fh)["interval"] == 600


def test_errors_ring_buffer(app):
    for i in range(60):
        app.errors.push(CastError("e%d" % i, "error %d" % i))
    status, _, d = _json(app.base_url, "GET", "/api/errors")
    assert status == 200
    errors = d["errors"]
    assert len(errors) == 50
    assert errors[0]["code"] == "e10" and errors[0]["n"] == 11
    assert errors[-1]["code"] == "e59" and errors[-1]["n"] == 60
    assert all("at" in e for e in errors)
    assert d["seq"] == 60
    _, _, s = _json(app.base_url, "GET", "/api/status")
    assert s["errors"] == 50 and s["errors_seq"] == 60       # the count caps, the sequence does not
    app.errors.push(CastError("e60", "error 60"))
    _, _, s = _json(app.base_url, "GET", "/api/status")
    assert s["errors"] == 50 and s["errors_seq"] == 61       # what the UI watches for new errors


def test_mutations_require_post(app):
    for path in ("/api/stop", "/api/cast", "/api/show", "/api/show/pause", "/api/tv/discover",
                 "/api/tv/select"):
        status, headers, d = _json(app.base_url, "GET", path)
        assert status == 405, path
        assert headers["Allow"] == "POST"
        assert d["error"]["code"] == "method_not_allowed"
    status, headers, _ = _json(app.base_url, "POST", "/api/status", {})
    assert status == 405 and headers["Allow"] == "GET"
    # and the connection is still usable afterwards: framing survived the 405
    status, _, body, conn = request(app.base_url, "GET", "/api/stop")
    assert status == 405
    status, _, _, _ = request(app.base_url, "GET", "/api/status", conn=conn)
    assert status == 200


def test_bad_bodies_are_400(app):
    status, _, d = _json(app.base_url, "POST", "/api/cast", b"{not json")
    assert status == 400 and d["error"]["code"] == "bad_request"
    status, _, d = _json(app.base_url, "POST", "/api/cast", [1, 2])
    assert status == 400
    status, _, d = _json(app.base_url, "POST", "/api/cast", {"source": "local"})
    assert status == 400 and "id" in d["error"]["message"]
    status, _, d = _json(app.base_url, "POST", "/api/show", {"items": []})
    assert status == 400


def test_cast_unknown_source_is_404(app):
    status, _, d = _json(app.base_url, "POST", "/api/cast", {"source": "gopro", "id": "x"})
    assert status == 404 and d["error"]["code"] == "unknown_source"
    status, _, d = _json(app.base_url, "POST", "/api/cast", {"source": "local", "id": "/nope"})
    assert status == 404 and d["error"]["code"] == "unknown_item"
    status, _, d = _json(app.base_url, "GET", "/api/sources/local/list")
    assert status == 404
    status, _, d = _json(app.base_url, "GET", "/api/sources/gopro/status")
    assert status == 404 and d["error"]["code"] == "unknown_source"


def test_cast_and_stop_over_api(app, tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\0" * 100)
    item = item_for_path(str(clip))
    app.local.remember(item)
    token = item.source_id
    assert token != str(clip) and "/" not in token       # opaque: the path never leaves the process
    app.tv_fake.video_script = ["PLAYING"]
    _, _, s = _json(app.base_url, "GET", "/api/status")
    assert s["session"] == [{"source": "local", "id": token, "name": "clip", "kind": "video",
                             "date": None, "width": None, "height": None, "duration": None,
                             "size": 100, "thumb": None, "warn": None, "variants": None,
                             "mime": "video/mp4"}]
    assert str(tmp_path) not in json.dumps(s)
    status, _, d = _json(app.base_url, "POST", "/api/cast", {"source": "local", "id": str(clip)})
    assert status == 404 and d["error"]["code"] == "unknown_item"   # paths are not ids
    status, _, d = _json(app.base_url, "POST", "/api/cast", {"source": "local", "id": token})
    assert status == 202 and d["cast"]["state"] in ("preparing", "starting", "playing")
    assert d["cast"]["id"] is None or str(tmp_path) not in json.dumps(d)

    def playing():
        _, _, s = _json(app.base_url, "GET", "/api/status")
        return s["cast"] and s["cast"]["state"] == "playing"
    wait_for(playing)
    _, _, s = _json(app.base_url, "GET", "/api/status")
    assert s["cast"]["name"] == "clip" and s["cast"]["position"] == "0:00:01"
    status, _, d = _json(app.base_url, "POST", "/api/stop")
    assert status == 200 and d["cast"]["state"] == "stopped"
    assert "Stop" in app.tv_fake.actions()


def test_show_over_api(app, tmp_path):
    ids = []
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        p = tmp_path / name
        p.write_bytes(make.jpeg(64, 48))
        item = item_for_path(str(p))
        app.local.remember(item)
        ids.append(item.source_id)
    status, _, d = _json(app.base_url, "POST", "/api/show",
                         {"items": [{"source": "local", "id": i} for i in ids], "interval": 5})
    assert status == 202
    assert d["show"]["total"] == 3 and d["show"]["interval"] == 5
    wait_for(lambda: app.show_now.current is not None and app.show_now.current.sent.is_set())
    status, _, d = _json(app.base_url, "POST", "/api/show/next")
    assert status == 200
    wait_for(lambda: len(app.tv_fake.uris) == 2)
    status, _, d = _json(app.base_url, "POST", "/api/show/pause")
    assert d["show"]["state"] == "paused"
    status, _, d = _json(app.base_url, "POST", "/api/show/resume")
    assert d["show"]["state"] == "playing"
    status, _, d = _json(app.base_url, "POST", "/api/settings", {"interval": 3})
    assert status == 200 and app.show_now.interval == 3.0       # the running show follows
    status, _, d = _json(app.base_url, "POST", "/api/show/stop")
    assert status == 200
    wait_for(lambda: app.show_now.terminal)
    assert app.show_now.state == "stopped"
    status, _, d = _json(app.base_url, "POST", "/api/show/bogus")
    assert status == 404
    _, _, s = _json(app.base_url, "GET", "/api/status")
    assert s["show"]["state"] == "stopped" and s["show"]["id"] == app.show_now.generation


def test_show_size_is_checked_before_any_resolve(app):
    src = _FakeSource("http://127.0.0.1:1")
    app.sources["fake"] = src
    too_many = [{"source": "fake", "id": str(i)} for i in range(MAX_SHOW_ITEMS + 1)]
    status, _, d = _json(app.base_url, "POST", "/api/show", {"items": too_many})
    assert status == 400 and d["error"]["code"] == "show_too_large"
    assert src.resolved == []                              # not one upstream call


def test_show_controls_without_show_are_400(app):
    status, _, d = _json(app.base_url, "POST", "/api/show/pause")
    assert status == 400 and d["error"]["code"] == "no_show"


class _FakeSource:
    name = "fake"

    def __init__(self, base):
        self.base = base
        self.connected_with = []
        self.resolved = []
        self.thumbed = []

    def status(self):
        return {"state": "connected", "detail": {}}

    def connect(self, params):
        self.connected_with.append(params)
        return self.status()

    def disconnect(self):
        pass

    def list(self, path=None, page=None):
        return Listing()

    def resolve(self, source_id, quality="auto"):
        self.resolved.append(source_id)
        raise CastError("nope", "no")

    def thumb(self, source_id):
        self.thumbed.append(source_id)
        if source_id == "none":
            return None
        return Upstream(self.base + "/" + urllib.parse.quote(source_id, safe=""),
                        headers={"Authorization": "Bearer t"})


def test_thumb_route_proxies_and_404s(app, upstream):
    up = upstream(b"\xff\xd8thumb-bytes", ctype="image/jpeg", statuses={"/gone": 403})
    app.sources["fake"] = _FakeSource(up.base)
    status, headers, body, conn = request(app.base_url, "GET", "/api/sources/fake/thumb/ok")
    assert status == 200
    assert body == b"\xff\xd8thumb-bytes"
    assert headers["Content-Type"] == "image/jpeg"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Cache-Control"] == "private, max-age=3600"
    assert up.requests[-1]["headers"].get("Authorization") == "Bearer t"
    # the id is decoded exactly once: an id holding a literal "%25" or "%2F" arrives intact,
    # and one holding a "/" (sent as %2F) arrives as "/"
    status, _, _, conn = request(app.base_url, "GET", "/api/sources/fake/thumb/a%2525b%252Fc", conn=conn)
    assert status == 200 and app.sources["fake"].thumbed[-1] == "a%25b%2Fc"
    status, _, _, conn = request(app.base_url, "GET", "/api/sources/fake/thumb/x%2Fy", conn=conn)
    assert status == 200 and app.sources["fake"].thumbed[-1] == "x/y"
    status, _, body, _ = request(app.base_url, "GET", "/api/sources/fake/thumb/none", conn=conn)
    assert status == 404
    status, _, body, _ = request(app.base_url, "GET", "/api/sources/fake/thumb/gone", conn=conn)
    assert status == 502
    assert json.loads(body)["error"]["code"] == "thumb_refused"
    # the source's other routes are delegated too
    status, _, body, _ = request(app.base_url, "GET", "/api/sources/fake/list", conn=conn)
    assert status == 200 and json.loads(body) == {"items": [], "folders": [], "next": None, "crumbs": []}
    status, _, body, _ = request(app.base_url, "GET", "/api/status", conn=conn)
    assert json.loads(body)["sources"] == {"fake": {"state": "connected", "detail": {}}}


def test_thumb_route_serves_raster_images_only(app, upstream):
    """HTML or SVG proxied under /api would be a same-origin document; only raster types pass."""
    for ctype, body in (("text/html", b"<script>1</script>"), ("image/svg+xml", b"<svg/>"),
                        (None, b"\x89PNG"), ("", b"\x89PNG"), ("application/octet-stream", b"x")):
        up = upstream(body, ctype=ctype)
        app.sources["fake"] = _FakeSource(up.base)
        status, headers, out, _ = request(app.base_url, "GET", "/api/sources/fake/thumb/x")
        assert status == 502, ctype
        assert json.loads(out)["error"]["code"] == "thumb_not_image", ctype
        assert headers["Content-Type"].startswith("application/json")
    for ctype in ("image/png", "image/webp", "image/gif", "IMAGE/JPEG; charset=binary"):
        up = upstream(b"\x89PNG", ctype=ctype)
        app.sources["fake"] = _FakeSource(up.base)
        status, headers, out, _ = request(app.base_url, "GET", "/api/sources/fake/thumb/x")
        assert status == 200 and out == b"\x89PNG", ctype
        assert headers["Content-Type"] == ctype.split(";")[0].lower()


def test_connect_body_is_one_dict(app):
    src = _FakeSource("http://127.0.0.1:1")
    app.sources["fake"] = src
    status, _, d = _json(app.base_url, "POST", "/api/sources/fake/connect", {"self": 1, "token": "t"})
    assert status == 200 and d == {"state": "connected", "detail": {}}
    assert src.connected_with == [{"self": 1, "token": "t"}]   # "self" is data, not a parameter name
