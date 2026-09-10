"""Google Photos share links: the page is scraped for a stream address.

Google offers no API for this: since 31 March 2025 the Photos Library API only
exposes items the user explicitly picks. Moved from ``cast-photos`` as it was,
with ``die()`` replaced by exceptions; the Picker API (Phase 6) becomes the main
path and this stays the fallback for links from other people's libraries.
"""
from __future__ import annotations

import re

from castlib import net
from castlib.errors import AuthError, NotMedia, UpstreamError
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


def resolve(link, op):
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

    status, html, final = net.fetch(link, op)
    if "accounts.google.com" in final or status in (401, 403):
        raise AuthError("login_required", "Google asked for a login." + HOW_TO_GET_COOKIES,
                        source="link")
    if status >= 400:
        raise UpstreamError("page_http",
                            "The page answered %d - the link expired or is private.%s"
                            % (status, HOW_TO_GET_COOKIES), source="link")

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
                   "Found %d addresses, none of which serves video - they are probably\n"
                   "stills, or Google changed the page format. Send the link over and the\n"
                   "parser can be adjusted." % len(found), source="link")
