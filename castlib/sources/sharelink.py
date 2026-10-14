"""Google Photos share links: the page is scraped for a stream address.

Google offers no API for this: since 31 March 2025 the Photos Library API only
exposes items the user explicitly picks. Moved from ``cast-photos`` as it was,
with ``die()`` replaced by exceptions; the Picker API (Phase 6) becomes the main
path and this stays the fallback for links from other people's libraries.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from castlib import net
from castlib.errors import AuthError, CastError, ConfigError, NotMedia, UpstreamError
from castlib.media import probe_media

# tried in order: full download first, then progressively smaller streams
SUFFIXES = ["=dv", "=m37", "=m22", "=m18"]
# hosts where Google serves the media itself rather than a page
MEDIA_HOST = re.compile(
    r'https://(?:(?:lh\d|ci\d?|yt\d)\.googleusercontent\.com'
    r'|video-downloads\.googleusercontent\.com'
    r'|photos\.fife\.usercontent\.google\.com)/')
HOW_TO_GET_COOKIES = """
A private link needs your Google cookies:
  a "Get cookies.txt" style extension -> export for photos.google.com -> cookies.txt
  cast-photos <link> -c cookies.txt
A share link (Share -> Create link) needs none of this.
"""
# the link, every redirect it takes and every address it yields: https on the default port,
# no credentials, one of these hosts exactly, or a host under one of these domains
ALLOWED_HOSTS = ("photos.app.goo.gl", "goo.gl", "photos.google.com", "photos.fife.usercontent.google.com")
ALLOWED_DOMAINS = ("googleusercontent.com",
                   "googlevideo.com")    # =m37 and =m18 redirect to rr...googlevideo.com (probed 2026-09-13)
LOGIN_HOST = "accounts.google.com"
# a share page names what it shares: a video's carries og:video tags (og:video:type video/mp4),
# a photo's - a motion photo's too, whose =dv is its short clip - only og:image (compared 2026-09-19)
OG_VIDEO = re.compile(r'<meta\s+property="og:video')
OG_IMAGE = re.compile(r'<meta\s+property="og:image')
OG_IMAGE_TAG = re.compile(r'<meta\s[^>]*property="og:image"[^>]*>')
CONTENT = re.compile(r'\scontent="([^"]*)"')
# an album page carries one /share/<share id>/photo/<item id> link per item, a single item's page
# one (5 against 1 on the five pages measured 2026-10-13); a heuristic, not a documented structure
SHARE_ID = re.compile(r'/share/([A-Za-z0-9_\-]+)')
PHOTO_LINK = ("That link is to a photo. cast-photos casts videos from links; to cast the photo, "
              "paste the link into the Google Photos tab of cast-tv's page.")
ALBUM_LINK = ("That link is to an album, and album links are not cast yet; "
              "share a single photo or video instead.")
# on a photo page's og:image base (measured 2026-10-13): =d the full photo, =m37 a motion photo's
# clip as H.264 1080p (404 on a plain photo), =w400-h400 a tile-sized still
PHOTO, CLIP, THUMB = "=d", "=m37", "=w400-h400"


@dataclass(frozen=True)
class Shared:
    """What a share link holds: a video's stream address, or a photo's ``=d`` address with its
    motion clip (``None`` on a plain photo) and thumbnail."""
    kind: str                                    # "video" | "photo"
    url: str
    clip: str | None = None
    thumb: str | None = None


def allowed(url) -> bool:
    """Whether a share link may fetch ``url``: https on an allowed Google host, nothing else."""
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    if (parts.scheme != "https" or port not in (None, 443)
            or parts.username is not None or parts.password is not None):
        return False
    host = parts.hostname or ""
    return host in ALLOWED_HOSTS or any(host.endswith("." + domain) for domain in ALLOWED_DOMAINS)


class _GooglePhotosOnly(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only onto an ``allowed()`` address, decided before the hop is sent."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if target.hostname == LOGIN_HOST:        # the login page itself is never fetched
            raise AuthError("login_required", "Google asked for a login." + HOW_TO_GET_COOKIES,
                            source="link")
        if not allowed(newurl):
            raise UpstreamError("redirect_refused", "The link redirected away from Google Photos "
                                "(to %s); that address is not fetched." % (target.netloc or newurl[:80]),
                                source="link")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def opener(cookies_path=None):
    """The opener for everything a share link touches: its cookies, if any, behind ``_GooglePhotosOnly``."""
    return net.opener_for(cookies_path, _GooglePhotosOnly)


def unescape_google(text):
    """HTML and JSON from Google arrive doubly escaped."""
    return (text.replace("\\u003d", "=").replace("\\u0026", "&")
                .replace("\\/", "/").replace("\\u003f", "?"))


def variants(address):
    """Turn a media address into candidate video variants, keeping its query.

    An address copied off the page carries a thumbnail suffix
    (=w539-h959-s-k-no-gm), and anything after "?" (authuser=1) must survive.
    """
    base, _, query = address.partition("?")
    base = base.split("=")[0]
    tail = ("?" + query) if query else ""
    return [base + s + tail for s in SUFFIXES]


def candidates(html):
    """Addresses that could be a video stream, most promising first."""
    html = unescape_google(html)
    out, seen = [], set()

    def add(url):
        if url not in seen:
            seen.add(url)
            out.append(url)

    # 1. ready-made video download addresses
    for m in re.findall(r'https://video-downloads\.googleusercontent\.com/[^"\'\\ <>]+',
                        html):
        add(m)
    # 2. base media identifiers - we append our own suffixes
    bases = re.findall(
        r'https://(?:(?:lh\d|ci\d?|yt\d)\.googleusercontent\.com'
        r'|photos\.fife\.usercontent\.google\.com)/'
        r'(?:[A-Za-z0-9_\-]{1,12}/)*[A-Za-z0-9_\-]{20,}', html)
    for base in dict.fromkeys(bases):
        for variant in variants(base):
            add(variant)
    return out


def _variant_of(url):
    """The suffix that decides quality: =dv is the original, =m18 the smallest."""
    tail = url.split("?")[0].rsplit("=", 1)
    return "=" + tail[1] if len(tail) == 2 else "direct"


def _probe(url, op):
    try:
        return probe_media(url, opener=op)
    except UpstreamError:
        return None


def _no_media():
    return NotMedia("no_media", "No media found on that page.\n"
                    "If the link is private, add cookies.%s" % HOW_TO_GET_COOKIES, source="link")


def _guarded(link, cookies_path):
    """The opener for ``link``, or ``bad_link`` before any request when ``allowed()`` refuses it."""
    if not allowed(link):
        raise ConfigError("bad_link", "Only https links on photos.app.goo.gl or photos.google.com "
                          "(or a Google media address) are fetched.", source="link")
    return opener(cookies_path)


def _media_stream(link, op):
    """A media address pasted as a link: only the right variant is missing."""
    tries = [link] if "/video-downloads" in link else variants(link)
    for url in tries:
        info = _probe(url, op)
        if info:
            print("  match: %s %s, %s" % (_variant_of(url), info[1],
                                          net.human(info[2])))
            return url
    raise NotMedia("no_video",
                   "That address serves no video - Google answers 403.\n"
                   "It is an address from inside a logged-in page, valid only in your\n"
                   "session. Use Share -> Create link, or add cookies (-c)."
                   + HOW_TO_GET_COOKIES, source="link")


def _read_page(link, op):
    """The share page's text; an album is refused here, before anything reads its cover."""
    status, html, final_url = net.fetch(link, op)
    if status in (401, 403):                     # a redirect to the login page stops in _GooglePhotosOnly
        raise AuthError("login_required", "Google asked for a login." + HOW_TO_GET_COOKIES,
                        source="link")
    if status >= 400:
        raise UpstreamError("page_http",
                            "The page answered %d - the link expired or is private.%s"
                            % (status, HOW_TO_GET_COOKIES), source="link")
    if album_items(html, final_url) > 1:         # whatever its cover is, photo or video
        raise NotMedia("album_link", ALBUM_LINK, source="link")
    return html


def _video_stream(html, op):
    """The first candidate address on the page that answers as video."""
    found = candidates(html)
    if not found:
        raise _no_media()

    print("  probing %d candidate streams..." % len(found))
    for url in found:
        info = _probe(url, op)
        if info:
            print("  match: %s %s, %s" % (_variant_of(url), info[1],
                                          net.human(info[2])))
            return url
    raise NotMedia("no_stream",
                   "Found %d addresses, none of which serves video. A photo link is cast from\n"
                   "the Google Photos tab of cast-tv's page. If it is a video, Google may have\n"
                   "changed the page format - send the link over and the parser can be adjusted."
                   % len(found), source="link")


def _clip(url, op):
    """A motion photo's clip at ``url`` (base + ``=m37``), or None on a plain photo.

    ``probe_media()`` answers None to every HTTP error; here only a 404 means "no clip".
    Only a 200/206 video answer is a clip; other answers fail the paste, naming what came back.
    """
    req = urllib.request.Request(url, headers={"User-Agent": net.UA, "Range": "bytes=0-1"})
    try:
        with op.open(req, timeout=20) as r:
            status = r.status
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip()
    except urllib.error.HTTPError as e:
        e.close()
        if e.code == 404:
            return None
        raise UpstreamError("clip_probe_failed", "Google answered %d (%s) when asked for the "
                            "photo's motion clip; try again later."
                            % (e.code, e.headers.get("Content-Type") or "no type"), source="link")
    except CastError:
        raise                                    # a redirect guard's refusal keeps its own code
    except Exception as e:
        raise UpstreamError("probe_failed", "Could not fetch %s: %s" % (url, e), source="link")
    if status in (200, 206) and (
            ctype.startswith("video/") or ctype == "application/mp4"):
        print("  clip: %s %s" % (CLIP, ctype))
        return url
    raise UpstreamError("clip_probe_failed", "Google answered %d (%s) when asked for the photo's "
                        "motion clip; try again later." % (status, ctype or "no type"),
                        source="link")


def _photo(html, op):
    """A photo page: its ``=d`` address, its clip when it is a motion photo, its thumbnail."""
    base = og_image_base(html)
    if base is None:
        raise _no_media()
    info = probe_media(base + PHOTO, opener=op, kinds=("photo",))
    if not info:
        raise _no_media()
    print("  photo: %s %s, %s" % (PHOTO, info[1], net.human(info[2])))
    return Shared("photo", base + PHOTO, clip=_clip(base + CLIP, op), thumb=base + THUMB)


def resolve(link, cookies_path=None):
    """The stream address behind a share link, or behind a media address pasted as one.

    The page, every redirect and every probe go through ``opener()``: an address
    ``allowed()`` refuses is never sent a request. A photo link is refused before any
    probe: a motion photo's clip would pass as video.
    """
    op = _guarded(link, cookies_path)
    if MEDIA_HOST.match(link):
        return _media_stream(link, op)
    html = _read_page(link, op)
    if page_kind(html) == "photo":
        raise NotMedia("photo_link", PHOTO_LINK, source="link")
    return _video_stream(html, op)


def shared(link, cookies_path=None) -> Shared:
    """What a share link holds, read from one page fetch: a video or a photo, an album refused.

    Same guard as ``resolve()``. A page with no Open Graph tags is probed as a video, as before.
    """
    op = _guarded(link, cookies_path)
    if MEDIA_HOST.match(link):
        return Shared("video", _media_stream(link, op))
    html = _read_page(link, op)
    if page_kind(html) == "photo":
        return _photo(html, op)
    return Shared("video", _video_stream(html, op))


def album_items(html: str, final_url: str) -> int:
    """The distinct items a share page links to as ``/share/<its share id>/photo/<item id>``.

    Counted on the page text as fetched; 0 when ``final_url`` is not a ``/share/`` page.
    """
    m = SHARE_ID.search(urllib.parse.urlsplit(final_url).path)
    if not m:
        return 0
    items = re.findall(re.escape("/share/%s/photo/" % m.group(1)) + r"([A-Za-z0-9_\-]+)", html)
    return len(set(items))


def og_image_base(html: str) -> str | None:
    """The ``og:image`` address up to its first ``=``, when it is a Google media address."""
    tag = OG_IMAGE_TAG.search(html)
    content = tag and CONTENT.search(tag.group(0))
    if not content:
        return None
    base = content.group(1).split("=")[0]
    return base if allowed(base) and MEDIA_HOST.match(base) else None


def page_kind(html: str) -> str | None:
    """``"video"`` or ``"photo"`` as the share page's Open Graph tags say, None when it has neither."""
    if OG_VIDEO.search(html):
        return "video"
    if OG_IMAGE.search(html):
        return "photo"
    return None
