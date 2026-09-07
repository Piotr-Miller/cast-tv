"""Wspólne części dla cast-gopro i cast-photos.

Obie komendy robią to samo w dwóch krokach: zamieniają adres strony albo wpis
w bibliotece na bezpośredni adres strumienia, a potem oddają go cast-tv, które
przepuszcza dane do telewizora. Nic nie ląduje na dysku.
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
    """Opener urllib z ciasteczkami w formacie Netscape (albo bez nich)."""
    if not cookies_path:
        return urllib.request.build_opener()
    jar = http.cookiejar.MozillaCookieJar()
    try:
        jar.load(os.path.abspath(cookies_path), ignore_discard=True, ignore_expires=True)
    except Exception as e:
        die("Nie wczytałem ciasteczek z %s: %s" % (cookies_path, e))
    print("  ciasteczka: %d wpisów" % len(jar))
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def fetch(url, op=None, headers=None, limit=6_000_000):
    """Pobiera stronę/JSON. Zwraca (status, tekst, adres_końcowy)."""
    req = urllib.request.Request(url, headers=dict(
        {"User-Agent": UA, "Accept-Language": "pl,en;q=0.8"}, **(headers or {})))
    try:
        with (op.open(req, timeout=30) if op else
              urllib.request.urlopen(req, timeout=30)) as r:
            return r.status, r.read(limit).decode("utf-8", "replace"), r.url
    except urllib.error.HTTPError as e:
        return e.code, e.read(limit).decode("utf-8", "replace"), url
    except Exception as e:
        die("Nie udało się pobrać %s: %s" % (url, e))


def is_video(url, op=None, headers=None):
    """Sprawdza pierwszym bajtem, czy adres naprawdę oddaje wideo.

    HEAD bywa blokowany na googleusercontent, więc pytamy o zakres 0-1 bajtu.
    Zwraca (content_type, rozmiar_lub_None) albo None.
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
            if ctype.startswith("video/") or ctype in (
                    "application/octet-stream", "application/mp4"):
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
    """cast-tv leży obok tego pliku (symlink w ~/.local/bin też zadziała)."""
    here = os.path.dirname(os.path.realpath(__file__))
    local = os.path.join(here, "cast-tv")
    return local if os.access(local, os.X_OK) else "cast-tv"


def cast(url, tv=None, cookies=None, port=None, title=None):
    """Oddaje adres do cast-tv, które przepuszcza strumień do telewizora."""
    cmd = [cast_tv_path(), url]
    if tv:
        cmd += ["-t", tv]
    if cookies:
        cmd += ["-c", cookies]
    if port:
        cmd += ["-p", str(port)]
    if title:
        print("▶  %s" % title, flush=True)   # przed oddaniem stdout do cast-tv
    try:
        return subprocess.call(cmd)
    except FileNotFoundError:
        die("Nie znalazłem cast-tv w PATH ani obok %s" % __file__)


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
