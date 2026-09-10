import socket

import pytest

from castlib.errors import UpstreamError
from castlib.items import MediaItem
from castlib.media import didl, kind_of_extension, probe_media


def test_probe_accepts_octet_stream(upstream):
    up = upstream(b"x" * 1000, ctype="binary/octet-stream")
    assert probe_media(up.base + "/GX010042") == ("video", "binary/octet-stream", 1000)
    assert up.requests[0]["headers"]["Range"] == "bytes=0-1"


def test_probe_rejects_a_page(upstream):
    up = upstream(b"<html>", ctype="text/html")
    assert probe_media(up.base + "/index") is None


def test_probe_http_error_is_not_media(upstream):
    up = upstream(b"", statuses={"/gone": 403})
    assert probe_media(up.base + "/gone") is None


def test_probe_network_failure_raises():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with pytest.raises(UpstreamError):
        probe_media("http://127.0.0.1:%d/clip.mp4" % port)


def test_kind_of_extension():
    assert kind_of_extension(".MKV") == "video"
    assert kind_of_extension(".mp3") == "audio"
    assert kind_of_extension(".srt") is None
    assert kind_of_extension(".xyz") is None


def test_didl_video_shape():
    item = MediaItem(kind="video", title="A & B", mime="video/x-matroska", source="local",
                     source_id="/f.mkv", path="/f.mkv", size=1234,
                     caption=("/f.srt", "http://h:1/m/t/s"))
    out = didl(item, "http://h:1/m/t/v")
    assert "object.item.videoItem" in out
    assert "A &amp; B" in out
    assert 'protocolInfo="http-get:*:video/x-matroska:DLNA.ORG_OP=01' in out
    assert 'size="1234"' in out
    assert 'sec:type="srt"' in out
    assert "http://h:1/m/t/s" in out
    assert "<" not in out and ">" not in out
