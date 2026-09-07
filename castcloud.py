"""Shared parts of cast-gopro and cast-photos.

Both commands do the same two things: turn a link, or an entry in a cloud
library, into a direct stream address, and then hand that to cast-tv, which
relays it to the TV. Nothing is written to disk.
"""
import http.cookiejar
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36")
CACHE = os.path.expanduser("~/.cache/cast-tv")
CONFIG = os.path.expanduser("~/.config/cast-tv")


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def opener_for(cookies_path):
    """A urllib opener carrying a Netscape cookie jar, or a plain one."""
    if not cookies_path:
        return urllib.request.build_opener()
    jar = http.cookiejar.MozillaCookieJar()
    try:
        jar.load(os.path.abspath(cookies_path), ignore_discard=True, ignore_expires=True)
    except Exception as e:
        die("Could not read cookies from %s: %s" % (cookies_path, e))
    print("  cookies: %d entries" % len(jar))
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def fetch(url, op=None, headers=None, limit=6_000_000):
    """Fetch a page or JSON document. Returns (status, text, final_url)."""
    req = urllib.request.Request(url, headers=dict(
        {"User-Agent": UA, "Accept-Language": "en;q=0.9"}, **(headers or {})))
    try:
        with (op.open(req, timeout=30) if op else
              urllib.request.urlopen(req, timeout=30)) as r:
            return r.status, r.read(limit).decode("utf-8", "replace"), r.url
    except urllib.error.HTTPError as e:
        return e.code, e.read(limit).decode("utf-8", "replace"), url
    except Exception as e:
        die("Could not fetch %s: %s" % (url, e))


def is_video(url, op=None, headers=None):
    """Ask for one byte to find out whether an address really serves video.

    HEAD is often refused on googleusercontent, hence the range request.
    Returns (content_type, size_or_None), or None.
    """
    req = urllib.request.Request(url, headers=dict(
        {"User-Agent": UA, "Range": "bytes=0-1"}, **(headers or {})))
    try:
        with (op.open(req, timeout=20) if op else
              urllib.request.urlopen(req, timeout=20)) as r:
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip()
            rng = r.headers.get("Content-Range") or ""
            size = None
            if "/" in rng and rng.rsplit("/", 1)[1].isdigit():
                size = int(rng.rsplit("/", 1)[1])
            elif r.headers.get("Content-Length", "").isdigit():
                size = int(r.headers["Content-Length"])
            # CDNs label video inconsistently - GoPro serves its source files as
            # binary/octet-stream - so Content-Type alone cannot be trusted.
            path = urllib.parse.urlparse(url).path.lower()
            if (ctype.startswith("video/")
                    or ctype.endswith("/octet-stream")
                    or ctype == "application/mp4"
                    or path.endswith((".mp4", ".m4v", ".mov", ".mkv", ".ts"))):
                return ctype, size
            return None
    except Exception:
        return None


def human(size):
    if not size:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return "%.0f %s" % (size, unit) if unit != "GB" else "%.1f GB" % size
        size /= 1024.0


def cast_tv_path():
    """cast-tv sits next to this file (a symlink in ~/.local/bin works too)."""
    here = os.path.dirname(os.path.realpath(__file__))
    local = os.path.join(here, "cast-tv")
    return local if os.access(local, os.X_OK) else "cast-tv"


def cast(url, tv=None, cookies=None, port=None, title=None):
    """Hand the address to cast-tv, which relays the stream to the TV."""
    cmd = [cast_tv_path(), url]
    if tv:
        cmd += ["-t", tv]
    if cookies:
        cmd += ["-c", cookies]
    if port:
        cmd += ["-p", str(port)]
    if title:
        cmd += ["--title", title]   # the name at the source is often meaningless
    try:
        return subprocess.call(cmd)
    except FileNotFoundError:
        die("cast-tv is neither in PATH nor next to %s" % __file__)


def cache_write(name, data):
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, name), "w") as fh:
        json.dump(data, fh)


def cache_read(name):
    try:
        with open(os.path.join(CACHE, name)) as fh:
            return json.load(fh)
    except Exception:
        return None
