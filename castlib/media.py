"""The media table: MIME types, kinds, the DIDL builder, DLNA headers, the probe.

One table with one fallback. The two lookups the script kept (``video/mpeg``
for the DIDL, ``application/octet-stream`` on the wire) disagreed for every
unknown extension; here the item carries its MIME and every path reads it.
"""
from __future__ import annotations

import sys
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
        ".smi": "application/smil", ".ass": "text/plain", ".vtt": "text/vtt",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".heic": "image/heic", ".heif": "image/heif", ".webp": "image/webp",
        ".gif": "image/gif"}

SUBTITLE_EXTENSIONS = (".srt", ".smi", ".ass", ".vtt")

# The one filter every source applies before it lists a photo: GIF, raw and
# unknown image types are hidden, not greyed.
PHOTO_MIMES = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}

# Video profile: byte seeking allowed, streaming flags. Sent as the
# contentFeatures header and embedded in the DIDL protocolInfo. First-commit
# values that the TV has accepted ever since; never edited.
DLNA_FEATURES = ("DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS="
                 "01700000000000000000000000000000")

# Photo profile: no seeking, interactive transfer. DLNA-guideline defaults,
# verified against the Samsung in Phase 2; this string and photo_profile()
# are the only places to change if the TV wants something else.
PHOTO_FEATURES = ("DLNA.ORG_PN={pn};DLNA.ORG_OP=00;DLNA.ORG_CI=0;DLNA.ORG_FLAGS="
                  "00900000000000000000000000000000")
PHOTO_MAX = 4096          # anything larger is downscaled to fit PHOTO_MAX x PHOTO_MAX

_hidden_kinds_logged: set = set()


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


def is_allowed_photo(mime) -> bool:
    return (mime or "").split(";")[0].strip().lower() in PHOTO_MIMES


def photo_profile(mime: str, width: int, height: int) -> str:
    """The DLNA.ORG_PN for a *prepared* photo: chosen from the result, never the source."""
    if mime == "image/png":
        return "PNG_LRG"
    if width <= 640 and height <= 480:
        return "JPEG_SM"
    if width <= 1024 and height <= 768:
        return "JPEG_MED"
    return "JPEG_LRG"


def photo_features(prepared) -> str:
    return PHOTO_FEATURES.format(pn=prepared.profile)


def dlna_headers(item) -> list[tuple[str, str]]:
    """The two headers DLNA renderers expect on every media response, per kind."""
    if item.kind == "photo" and item.prepared is not None:
        return [("transferMode.dlna.org", "Interactive"),
                ("contentFeatures.dlna.org", photo_features(item.prepared))]
    # Everything else is served as the script always served it, subtitles included.
    return [("transferMode.dlna.org", "Streaming"),
            ("contentFeatures.dlna.org", DLNA_FEATURES)]


def kind_from_facets(source: str, data: dict) -> str | None:
    """``"video"``, ``"photo"`` or ``None`` (hidden) from a source's own metadata.

    Pure: ``data`` is the listing entry as the API returned it. Graph entries
    carry ``folder``/``file``/``image``/``photo``/``video`` facets, Picker items
    ``type`` plus ``mediaFile.mimeType``, GoPro entries a ``type`` string.
    """
    if source == "onedrive":
        if "folder" in data:
            return None
        if "video" in data:
            return "video"
        mime = (data.get("file") or {}).get("mimeType") or ""
        if ("image" in data or "photo" in data or mime.startswith("image/")) \
                and is_allowed_photo(mime):
            return "photo"
        return None
    if source == "gphotos":
        t = (data.get("type") or "").upper()
        if t == "VIDEO":
            return "video"
        if t == "PHOTO" and is_allowed_photo((data.get("mediaFile") or {}).get("mimeType")):
            return "photo"
        return None
    if source == "gopro":
        t = (data.get("type") or "").lower()
        if t in ("video", "mp4", "multiclipedit", "timelapsevideo", "looping"):
            return "video"
        if t in ("photo", "burst", "timelapse", "livephoto"):
            return "photo"
        return None
    return None


def note_hidden_kind(source: str, value) -> bool:
    """Log an unfamiliar kind once per session; returns True the first time."""
    key = (source, repr(value))
    if key in _hidden_kinds_logged:
        return False
    _hidden_kinds_logged.add(key)
    sys.stderr.write("   ! %s: hiding an item of unknown kind %r\n" % (source, value))
    return True


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
    if item.kind == "photo" and item.prepared is not None:
        # the TV is told about the file it will fetch, never about the source
        prep = item.prepared
        attrs = 'protocolInfo="http-get:*:%s:%s"' % (prep.mime, photo_features(prep))
        attrs += ' resolution="%dx%d" size="%d"' % (prep.width, prep.height, prep.size)
    else:
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


def probe_media(url: str, headers=None, opener=None, kinds=("video",)):
    """Ask for one byte to find out whether an address really serves media.

    HEAD is often refused on googleusercontent, hence the range request.
    Returns ``(kind, content_type, size_or_None)``, or ``None`` when the
    address answers but not with one of ``kinds`` (``"video"`` by default, so
    the share-link scrapers keep skipping stills; ``("photo",)`` accepts JPEG,
    PNG and WebP answers). A network failure raises ``UpstreamError``
    instead of being mistaken for "not media".
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
    if "photo" in kinds and (is_allowed_photo(ctype) or (
            ctype.endswith("/octet-stream")          # GoPro's CDN labels its JPEGs so (probed 2026-09-12)
            and path.endswith((".jpg", ".jpeg", ".png", ".webp")))):
        return "photo", ctype, size
    if "video" in kinds and (
            ctype.startswith("video/")
            or ctype.endswith("/octet-stream")
            or ctype == "application/mp4"
            or path.endswith((".mp4", ".m4v", ".mov", ".mkv", ".ts"))):
        return "video", ctype, size
    return None
