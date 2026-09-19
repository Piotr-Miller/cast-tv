"""Google Photos share links: the page is scraped for a stream address.

Google offers no API for this: since 31 March 2025 the Photos Library API only
exposes items the user explicitly picks. Moved from ``cast-photos`` as it was,
with ``die()`` replaced by exceptions; the Picker API (Phase 6) becomes the main
path and this stays the fallback for links from other people's libraries.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request

from castlib import net
from castlib.errors import AuthError, ConfigError, NotMedia, UpstreamError
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
PHOTO_LINK = ("That link is to a photo. Share links cast videos only; to cast a photo, pick it in "
              "Google's picker instead (the Google Photos tab, or cast-photos --pick).")


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


def resolve(link, cookies_path=None):
    """The stream address behind a share link, or behind a media address pasted as one.

    The page, every redirect and every probe go through ``opener()``: an address
    ``allowed()`` refuses is never sent a request.
    """
    if not allowed(link):
        raise ConfigError("bad_link", "Only https links on photos.app.goo.gl or photos.google.com "
                          "(or a Google media address) are fetched.", source="link")
    op = opener(cookies_path)
    if MEDIA_HOST.match(link):
        # already a media address - only the right variant is missing
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

    status, html, _ = net.fetch(link, op)
    if status in (401, 403):                     # a redirect to the login page stops in _GooglePhotosOnly
        raise AuthError("login_required", "Google asked for a login." + HOW_TO_GET_COOKIES,
                        source="link")
    if status >= 400:
        raise UpstreamError("page_http",
                            "The page answered %d - the link expired or is private.%s"
                            % (status, HOW_TO_GET_COOKIES), source="link")

    if page_kind(html) == "photo":             # before any probe: a motion photo's clip would pass as video
        raise NotMedia("photo_link", PHOTO_LINK, source="link")

    found = candidates(html)
    if not found:
        raise NotMedia("no_media", "No media found on that page.\n"
                       "If the link is private, add cookies.%s" % HOW_TO_GET_COOKIES,
                       source="link")

    print("  probing %d candidate streams..." % len(found))
    for url in found:
        info = _probe(url, op)
        if info:
            print("  match: %s %s, %s" % (_variant_of(url), info[1],
                                          net.human(info[2])))
            return url
    raise NotMedia("no_stream",
                   "Found %d addresses, none of which serves video. Share links cast videos only:\n"
                   "if this is a photo, pick it in Google's picker instead (the Google Photos tab,\n"
                   "or cast-photos --pick). If it is a video, Google may have changed the page\n"
                   "format - send the link over and the parser can be adjusted." % len(found),
                   source="link")


def page_kind(html: str) -> str | None:
    """``"video"`` or ``"photo"`` as the share page's Open Graph tags say, None when it has neither."""
    if OG_VIDEO.search(html):
        return "video"
    if OG_IMAGE.search(html):
        return "photo"
    return None
