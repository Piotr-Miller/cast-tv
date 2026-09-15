"""Small HTTP helpers shared by the cloud resolvers."""
from __future__ import annotations

import http.cookiejar
import os
import urllib.error
import urllib.parse
import urllib.request

from castlib.errors import CastError, ConfigError, UpstreamError

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: a 3xx surfaces as ``HTTPError`` instead of being followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


NO_REDIRECT = urllib.request.build_opener(_NoRedirect)
"""The opener for calls that carry a bearer or a secret: the default redirect handler
copies every header, ``Authorization`` included, onto the redirected request."""


def _origin(url: str) -> tuple | None:
    """``(scheme, host, port)`` with the default port filled in; ``None`` when the port is unreadable."""
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    try:
        port = parts.port or {"http": 80, "https": 443}.get(scheme)
    except ValueError:
        return None
    return scheme, (parts.hostname or "").lower(), port


class _DropAuthAcrossOrigins(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but carry ``Authorization`` only to the same scheme, host and port."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        origin = _origin(newurl)
        if new is not None and (origin is None or origin != _origin(req.full_url)):
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new


BEARER_SAFE = urllib.request.build_opener(_DropAuthAcrossOrigins)
"""The opener for media fetches: redirects are followed, the bearer stays on its origin
(another host, a TLS downgrade or another port drops it). Google Photos answers ``baseUrl=dv`` and ``=m37`` with a 302 to a host that needs no
bearer (probed 2026-09-13); the default handler would hand it over anyway."""


def opener_for(cookies_path: str | None, *handlers) -> urllib.request.OpenerDirector:
    """A urllib opener carrying a Netscape cookie jar, or a plain one; ``handlers`` join either."""
    if not cookies_path:
        return urllib.request.build_opener(*handlers)
    jar = http.cookiejar.MozillaCookieJar()
    try:
        jar.load(os.path.abspath(cookies_path), ignore_discard=True, ignore_expires=True)
    except Exception as e:
        raise ConfigError("cookies_unreadable",
                          "Could not read cookies from %s: %s" % (cookies_path, e))
    print("  cookies: %d entries" % len(jar))
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), *handlers)


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
    except CastError:
        raise                                    # a redirect guard's refusal keeps its own code
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
