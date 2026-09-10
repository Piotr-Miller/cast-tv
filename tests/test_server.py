import http.client
import json

from castlib.server import _host_only
from tests.conftest import request


def test_media_token_required(server, local_file):
    srv, base = server
    item, data = local_file(srv)
    status, headers, body, _ = request(base, "GET", "/m/wrongtoken/%s" % item.id)
    assert status == 404
    assert json.loads(body)["error"]["code"] == "not_found"
    status, _, body, _ = request(base, "GET", "/m/%s/nosuchid" % srv.media_token)
    assert status == 404
    status, _, body, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id))
    assert status == 200
    assert body == data


def test_api_rejects_foreign_origin(server):
    srv, base = server
    status, headers, body, _ = request(base, "GET", "/api/status",
                                       {"Origin": "http://evil"})
    assert status == 403
    assert headers["Content-Type"].startswith("application/json")
    assert json.loads(body)["error"]["code"] == "forbidden"
    # the same request with a matching Origin passes the check (404: no app yet)
    status, _, _, _ = request(base, "GET", "/api/status",
                              {"Origin": base})
    assert status == 404


def test_api_rejects_foreign_host(server):
    srv, base = server
    status, _, body, _ = request(base, "GET", "/api/status", {"Host": "evil.example:8895"})
    assert status == 403
    status, _, body, _ = request(base, "GET", "/api/status", {"Host": "127.0.0.1:%d" % srv.port})
    assert status == 404


def test_api_rejects_cross_site_fetch(server):
    srv, base = server
    status, _, _, _ = request(base, "POST", "/api/cast", {"Sec-Fetch-Site": "cross-site"})
    assert status == 403


def test_404_is_json_and_keeps_connection(server, local_file):
    srv, base = server
    item, data = local_file(srv)
    status, headers, body, conn = request(base, "GET", "/nope")
    assert status == 404
    assert headers["Content-Type"].startswith("application/json")
    assert json.loads(body)["error"]["code"] == "not_found"
    assert (headers.get("Connection") or "").lower() != "close"
    # second request on the same connection
    status, _, body, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id),
                                 conn=conn)
    assert status == 200
    assert body == data


def test_head_and_get_agree_on_length(server, local_file):
    srv, base = server
    item, data = local_file(srv)
    url = "/m/%s/%s" % (srv.media_token, item.id)
    s1, h1, b1, conn = request(base, "HEAD", url)
    s2, h2, b2, _ = request(base, "GET", url, conn=conn)
    assert (s1, s2) == (200, 200)
    assert h1["Content-Length"] == h2["Content-Length"] == str(len(data))
    assert b1 == b"" and b2 == data
    assert h2["transferMode.dlna.org"] == "Streaming"
    assert h2["contentFeatures.dlna.org"].startswith("DLNA.ORG_OP=01")


def test_root_redirects_and_favicon_is_empty(server):
    srv, base = server
    status, headers, body, conn = request(base, "GET", "/")
    assert status == 302 and headers["Location"] == "/ui/"
    status, headers, body, _ = request(base, "GET", "/favicon.ico", conn=conn)
    assert status == 204


def test_post_body_is_drained_under_keepalive(server):
    srv, base = server
    host = base.split("://", 1)[1]
    conn = http.client.HTTPConnection(host, timeout=5)
    conn.request("POST", "/api/cast", body=b'{"x": 1}',
                 headers={"Content-Type": "application/json", "Origin": "http://evil"})
    resp = conn.getresponse()
    resp.read()
    assert resp.status == 403
    conn.request("GET", "/favicon.ico")
    resp = conn.getresponse()
    resp.read()
    assert resp.status == 204


def test_caption_header_only_on_the_video(server, local_file, tmp_path):
    srv, base = server
    from castlib.items import MediaItem
    sub_path = tmp_path / "film.srt"
    sub_path.write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8")
    sub = srv.registry.add(MediaItem(kind="subtitle", title="film.srt",
                                     mime="application/x-subrip", source="local",
                                     source_id=str(sub_path), path=str(sub_path)))
    video, _ = local_file(srv, "film.mp4")
    video.caption = (str(sub_path), srv.media_url(sub))
    _, h_video, _, conn = request(base, "HEAD", "/m/%s/%s" % (srv.media_token, video.id))
    _, h_sub, _, _ = request(base, "HEAD", "/m/%s/%s" % (srv.media_token, sub.id), conn=conn)
    assert h_video["CaptionInfo.sec"] == srv.media_url(sub)
    assert "CaptionInfo.sec" not in h_sub


def test_host_only():
    assert _host_only("localhost:8895") == "localhost"
    assert _host_only("192.168.1.5") == "192.168.1.5"
    assert _host_only("[::1]:8895") == "::1"
    assert _host_only("") == ""
