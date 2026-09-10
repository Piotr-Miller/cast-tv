"""GoPro cloud: a pasted browser token, the media listing, signed download addresses.

Moved from ``cast-gopro`` as it was, with ``die()`` replaced by exceptions.
Phase 4 puts this on the ``Source`` contract.
"""
from __future__ import annotations

import json
import os
import re

from castlib import config, net
from castlib.errors import AuthError, ConfigError, NotMedia, UpstreamError
from castlib.media import probe_media

API = "https://api.gopro.com"
MEDIA_ACCEPT = "application/vnd.gopro.jk.media+json; version=2.0.0"
TOKEN_NAME = "gopro-token"
HOW_TO_GET_A_TOKEN = """
The token comes from a logged-in browser and lasts a few hours:

  1. open https://gopro.com/media-library/ and sign in
  2. F12 -> Application -> Storage -> Cookies -> https://gopro.com
  3. copy the value of gp_access_token (it starts with eyJ)
     or: F12 -> Network -> any api.gopro.com request -> Request Headers ->
         the part of "authorization" after "Bearer "
  4. cast-gopro --token eyJhbGc...
"""


def token_file() -> str:
    return os.path.join(config.config_dir(), TOKEN_NAME)


def token(explicit=None) -> str:
    if explicit:
        return explicit.strip()
    if os.environ.get("GOPRO_TOKEN"):
        return os.environ["GOPRO_TOKEN"].strip()
    try:
        with open(token_file(), encoding="utf-8") as fh:
            return fh.read().strip()
    except FileNotFoundError:
        raise AuthError("no_token", "No GoPro token stored." + HOW_TO_GET_A_TOKEN,
                        source="gopro")


def save_token(value: str) -> str:
    """Store the token (mode 0600); returns the path. A double paste is folded to one copy."""
    value = value.strip()
    # pasting twice in a row yields two copies glued together; the symmetry shows it
    if len(value) % 2 == 0 and value[:len(value) // 2] == value[len(value) // 2:]:
        value = value[:len(value) // 2]
        print("The token was pasted twice - storing one copy.")
    config.write_private(token_file(), value)
    return token_file()


def api(path: str, tok: str, params: str | None = None) -> dict:
    url = API + path + ("?" + params if params else "")
    status, body, _ = net.fetch(url, headers={
        "Authorization": "Bearer " + tok, "Accept": MEDIA_ACCEPT})
    if status == 401:
        raise AuthError("token_rejected",
                        "GoPro rejected the token (401) - expired or incomplete."
                        + HOW_TO_GET_A_TOKEN, source="gopro")
    if status >= 400:
        raise UpstreamError("gopro_http", "GoPro answered %d:\n%s" % (status, body[:400]),
                            source="gopro")
    try:
        return json.loads(body)
    except ValueError:
        raise UpstreamError("gopro_not_json", "GoPro's answer is not JSON:\n%s" % body[:400],
                            source="gopro")


def list_media(tok: str, count: int) -> list[dict]:
    data = api("/media/search", tok, params=(
        "fields=id,filename,captured_at,content_title,file_size,type,resolution,"
        "duration&order_by=captured_at&per_page=%d&page=1" % count))
    media = data.get("_embedded", {}).get("media")
    if media is None:
        raise UpstreamError("gopro_shape",
                            "Unfamiliar answer from GoPro (keys: %s).\n"
                            "Send it over and the parser can be adjusted."
                            % ", ".join(data)[:200], source="gopro")
    items = []
    for m in media:
        items.append({
            "id": m.get("id"),
            "name": m.get("content_title") or m.get("filename") or m.get("id"),
            "date": (m.get("captured_at") or "")[:10],
            "kind": m.get("type", ""),
            "size": m.get("file_size"),
            "res": m.get("resolution", ""),
        })
    config.cache_write("gopro-list.json", items)
    return items


def cached_listing():
    return config.cache_read("gopro-list.json")


def pick(what: str) -> dict:
    """The listing entry a number names, or a bare media id."""
    items = cached_listing()
    if what.isdigit() and items and 1 <= int(what) <= len(items):
        return items[int(what) - 1]
    if what.isdigit():
        raise ConfigError("no_listing", "No listing cached - run `cast-gopro` first.",
                          source="gopro")
    return {"id": what, "name": what}


def _rank(label):
    """Lower is better. The names come from what the API actually returns."""
    return {"source": 0, "high_res_proxy_mp4": 1, "high": 1, "high_res": 1,
            "mobile": 2, "file": 2, "edit_proxy": 3, "low": 4}.get(
        (label or "").lower(), 5)


def library_url(media_id: str, tok: str, quality: str = "auto") -> str:
    """Signed mp4 address for a cloud entry; best quality first."""
    data = api("/media/%s/download" % media_id, tok)
    emb = data.get("_embedded", {})
    options = []
    for var in emb.get("variations", []) or []:
        if (var.get("type") or "").lower() in ("mp4", "video", ""):
            options.append((_rank(var.get("label")), var.get("label", "?"),
                            var.get("url")))
    for f in emb.get("files", []) or []:
        # not the source: for the media tested these were 1280 px proxies
        options.append((_rank("file"), "file", f.get("url")))
    options = [o for o in options if o[2]]
    if not options:
        raise UpstreamError("gopro_no_download",
                            "No download address in GoPro's answer (keys: %s).\n"
                            "Send the JSON over and the parser can be adjusted."
                            % (", ".join(emb) or "-"), source="gopro", item=media_id)
    options.sort(key=lambda o: o[0])
    if quality == "proxy":          # a deliberately lighter file
        options = [o for o in options if o[0] > 0] or options
    elif quality == "source":
        options = [o for o in options if o[0] == 0] or options
    for _, label, url in options:
        info = _probe(url)
        if info:
            print("  quality: %s (%s, %s)" % (label, info[1], net.human(info[2])))
            return url
    print("  ! no variant confirmed itself as video, taking the first one")
    return options[0][2]


def _probe(url):
    """The one-byte probe, tolerant of a flaky CDN: a network error counts as "not this one"."""
    try:
        return probe_media(url)
    except UpstreamError:
        return None


def share_url(url: str) -> str:
    """Public gopro.com/v/... link - the address sits in JSON on the page."""
    _, html, _ = net.fetch(url)
    found = re.findall(r'https?://[^"\'\\ ]+?\.mp4[^"\'\\ ]*', html)
    # longest first: a signed source link is longer than a thumbnail's
    for candidate in sorted(set(found), key=len, reverse=True):
        candidate = candidate.replace("\\u0026", "&").replace("\\/", "/")
        if _probe(candidate):
            return candidate
    raise NotMedia("no_stream", "No stream found on that page.\n"
                   "Check the link is public (Share -> Copy link).", source="gopro")
