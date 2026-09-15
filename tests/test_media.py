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


def test_didl_photo():
    from castlib.photos import Prepared
    item = MediaItem(kind="photo", title="IMG_1", mime="image/heic", source="local",
                     source_id="/p.heic", path="/p.heic", size=999_999, width=4000, height=3000)
    item.prepared = Prepared("/tmp/x.jpg", "image/jpeg", 123_456, 3000, 4000, "JPEG_LRG")
    out = didl(item, "http://h:1/m/t/p")
    assert "object.item.imageItem.photo" in out
    assert 'protocolInfo="http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_LRG;DLNA.ORG_OP=00' in out
    assert 'resolution="3000x4000"' in out and 'size="123456"' in out
    assert "image/heic" not in out and "999999" not in out and "4000x3000" not in out


def test_photo_profile_from_result():
    from castlib.media import photo_profile
    assert photo_profile("image/jpeg", 4032, 3024) == "JPEG_LRG"
    assert photo_profile("image/jpeg", 640, 480) == "JPEG_SM"
    assert photo_profile("image/jpeg", 1024, 768) == "JPEG_MED"
    assert photo_profile("image/png", 4096, 4096) == "PNG_LRG"


def test_photo_headers_interactive():
    from castlib.media import dlna_headers
    from castlib.photos import Prepared
    item = MediaItem(kind="photo", title="p", mime="image/heic", source="local", source_id="p")
    item.prepared = Prepared("/tmp/x.jpg", "image/jpeg", 1, 100, 100, "JPEG_SM")
    headers = dict(dlna_headers(item))
    assert headers["transferMode.dlna.org"] == "Interactive"
    assert headers["contentFeatures.dlna.org"] == (
        "DLNA.ORG_PN=JPEG_SM;DLNA.ORG_OP=00;DLNA.ORG_CI=0;"
        "DLNA.ORG_FLAGS=00900000000000000000000000000000")
    video = MediaItem(kind="video", title="v", mime="video/mp4", source="local", source_id="v")
    assert dict(dlna_headers(video))["transferMode.dlna.org"] == "Streaming"


def test_kind_from_facets():
    from castlib.media import kind_from_facets
    graph_video = {"name": "a.mp4", "file": {"mimeType": "video/mp4"}, "video": {"bitrate": 1}}
    graph_photo = {"name": "a.heic", "file": {"mimeType": "image/heic"}, "image": {}, "photo": {}}
    graph_gif = {"name": "a.gif", "file": {"mimeType": "image/gif"}, "image": {}}
    graph_raw = {"name": "a.dng", "file": {"mimeType": "image/x-adobe-dng"}}
    graph_folder = {"name": "Camera Roll", "folder": {"childCount": 3}}
    graph_doc = {"name": "a.pdf", "file": {"mimeType": "application/pdf"}}
    assert kind_from_facets("onedrive", graph_video) == "video"
    assert kind_from_facets("onedrive", graph_photo) == "photo"
    assert kind_from_facets("onedrive", graph_gif) is None
    assert kind_from_facets("onedrive", graph_raw) is None
    assert kind_from_facets("onedrive", graph_folder) is None
    assert kind_from_facets("onedrive", graph_doc) is None
    picker_photo = {"type": "PHOTO", "mediaFile": {"mimeType": "image/jpeg"}}
    picker_gif = {"type": "PHOTO", "mediaFile": {"mimeType": "image/gif"}}
    picker_video = {"type": "VIDEO", "mediaFile": {"mimeType": "video/mp4"}}
    assert kind_from_facets("gphotos", picker_photo) == "photo"
    assert kind_from_facets("gphotos", picker_gif) is None
    assert kind_from_facets("gphotos", picker_video) == "video"
    assert kind_from_facets("gopro", {"type": "Video"}) == "video"
    assert kind_from_facets("gopro", {"type": "TimeLapseVideo"}) == "video"
    assert kind_from_facets("gopro", {"type": "Burst"}) == "photo"
    assert kind_from_facets("gopro", {"type": "LivePhoto"}) == "photo"
    assert kind_from_facets("gopro", {"type": "Audio"}) is None


def test_unknown_kind_hidden(capsys):
    from castlib import media
    from castlib.media import kind_from_facets, note_hidden_kind
    media._hidden_kinds_logged.clear()
    assert kind_from_facets("gopro", {"type": "Hologram"}) is None
    assert note_hidden_kind("gopro", "Hologram") is True
    assert note_hidden_kind("gopro", "Hologram") is False
    assert capsys.readouterr().err.count("Hologram") == 1
