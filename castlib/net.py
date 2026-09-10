"""Small HTTP helpers shared by the cloud resolvers."""
from __future__ import annotations

import http.cookiejar
import os
import urllib.error
import urllib.request

from castlib.errors import ConfigError, UpstreamError

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36")


def opener_for(cookies_path: str | None) -> urllib.request.OpenerDirector:
    """A urllib opener carrying a Netscape cookie jar, or a plain one."""
    if not cookies_path:
        return urllib.request.build_opener()
    jar = http.cookiejar.MozillaCookieJar()
    try:
        jar.load(os.path.abspath(cookies_path), ignore_discard=True, ignore_expires=True)
    except Exception as e:
        raise ConfigError("cookies_unreadable",
                          "Could not read cookies from %s: %s" % (cookies_path, e))
    print("  cookies: %d entries" % len(jar))
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def fetch(url: str, op=None, headers=None, limit: int = 6_000_000):
    """Fetch a page or JSON document. Returns (status, text, final_url).

    An HTTP error is an answer and comes back as its status; anything that
    stops an answer arriving raises ``UpstreamError``.
    """
    req = urllib.request.Request(url, headers=dict(
        {"User-Agent": UA, "Accept-Language": "en;q=0.9"}, **(headers or {})))
    try:
        with (op.open(req, timeout=30) if op else
              urllib.request.urlopen(req, timeout=30)) as r:
            return r.status, r.read(limit).decode("utf-8", "replace"), r.url
    except urllib.error.HTTPError as e:
        return e.code, e.read(limit).decode("utf-8", "replace"), url
    except Exception as e:
        raise UpstreamError("fetch_failed", "Could not fetch %s: %s" % (url, e))


def human(size) -> str:
    if not size:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return "%.0f %s" % (size, unit) if unit != "GB" else "%.1f GB" % size
        size /= 1024.0
    return "?"
