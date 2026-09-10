"""The media table: MIME types, kinds, the DIDL builder, DLNA headers, the probe.

One table with one fallback. The two lookups the script kept (``video/mpeg``
for the DIDL, ``application/octet-stream`` on the wire) disagreed for every
unknown extension; here the item carries its MIME and every path reads it.
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape

from castlib.errors import UpstreamError
from castlib.net import UA

MIME = {".mkv": "video/x-matroska", ".mp4": "video/mp4", ".m4v": "video/mp4",
        ".avi": "video/x-msvideo", ".mov": "video/quicktime", ".ts": "video/mpeg",
        ".m2ts": "video/mp2t", ".mpg": "video/mpeg", ".mpeg": "video/mpeg",
        ".webm": "video/webm", ".wmv": "video/x-ms-wmv", ".mp3": "audio/mpeg",
        ".flac": "audio/flac", ".m4a": "audio/mp4", ".srt": "application/x-subrip",
        ".smi": "application/smil", ".ass": "text/plain", ".vtt": "text/vtt"}

SUBTITLE_EXTENSIONS = (".srt", ".smi", ".ass", ".vtt")

# Video profile: byte seeking allowed, streaming flags. Sent as the
# contentFeatures header and embedded in the DIDL protocolInfo. First-commit
# values that the TV has accepted ever since; never edited.
DLNA_FEATURES = ("DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS="
                 "01700000000000000000000000000000")


def kind_of_extension(ext: str) -> str | None:
    """``"video"``, ``"audio"``, ``"photo"`` (Phase 2) or ``None`` for anything not castable."""
    mime = MIME.get(ext.lower())
    if not mime:
        return None
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("image/"):
        return "photo"
    return None


def dlna_headers(item) -> list[tuple[str, str]]:
    """The two headers DLNA renderers expect on every media response, per kind."""
    # Photos get their own profile in Phase 2; everything else is served as the
    # script always served it, subtitles included.
    return [("transferMode.dlna.org", "Streaming"),
            ("contentFeatures.dlna.org", DLNA_FEATURES)]


def _upnp_class(item) -> str:
    if item.kind == "photo":
        return "object.item.imageItem.photo"
    # Audio keeps the class the TV has always been told; it is CLI-only and
    # nothing has verified an audioItem class against this renderer.
    return "object.item.videoItem"


def didl(item, url: str) -> str:
    """DIDL-Lite metadata for ``SetAVTransportURI``, already XML-escaped for the SOAP body."""
    cap = ""
    if item.caption:
        sub_path, sub_url = item.caption
        ext = sub_path.rsplit(".", 1)[-1].lower() if "." in sub_path else ""
        cap = ('<sec:CaptionInfoEx sec:type="%s">%s</sec:CaptionInfoEx>'
               % (ext, escape(sub_url)))
    attrs = 'protocolInfo="http-get:*:%s:%s"' % (item.mime, DLNA_FEATURES)
    if item.width and item.height:
        attrs += ' resolution="%dx%d"' % (item.width, item.height)
    if item.size:
        attrs += ' size="%d"' % item.size
    return ('&lt;DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
            'xmlns:sec="http://www.sec.co.kr/"&gt;'
            '&lt;item id="1" parentID="0" restricted="1"&gt;'
            "&lt;dc:title&gt;%s&lt;/dc:title&gt;"
            "&lt;upnp:class&gt;%s&lt;/upnp:class&gt;%s"
            '&lt;res %s&gt;%s&lt;/res&gt;'
            "&lt;/item&gt;&lt;/DIDL-Lite&gt;"
            % (escape(item.title), _upnp_class(item),
               cap.replace("<", "&lt;").replace(">", "&gt;"),
               attrs, escape(url)))


def probe_media(url: str, headers=None, opener=None):
    """Ask for one byte to find out whether an address really serves media.

    HEAD is often refused on googleusercontent, hence the range request.
    Returns ``(kind, content_type, size_or_None)``, or ``None`` when the
    address answers but not with media. A network failure raises
    ``UpstreamError`` instead of being mistaken for "not media".
    """
    req = urllib.request.Request(url, headers=dict(
        {"User-Agent": UA, "Range": "bytes=0-1"}, **(headers or {})))
    try:
        with (opener.open(req, timeout=20) if opener else
              urllib.request.urlopen(req, timeout=20)) as r:
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip()
            rng = r.headers.get("Content-Range") or ""
            size = None
            if "/" in rng and rng.rsplit("/", 1)[1].isdigit():
                size = int(rng.rsplit("/", 1)[1])
            elif r.headers.get("Content-Length", "").isdigit():
                size = int(r.headers["Content-Length"])
    except urllib.error.HTTPError:
        return None
    except Exception as e:
        raise UpstreamError("probe_failed", "Could not fetch %s: %s" % (url, e))
    # CDNs label video inconsistently - GoPro serves its source files as
    # binary/octet-stream - so Content-Type alone cannot be trusted.
    path = urllib.parse.urlparse(url).path.lower()
    if (ctype.startswith("video/")
            or ctype.endswith("/octet-stream")
            or ctype == "application/mp4"
            or path.endswith((".mp4", ".m4v", ".mov", ".mkv", ".ts"))):
        return "video", ctype, size
    return None
