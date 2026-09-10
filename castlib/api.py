"""The JSON surface the UI polls and drives.

Every route arrives here after the handler's Origin/Host check. Mutations
are POST; every answer carries an exact ``Content-Length`` (the handler's
``_json``); errors are ``{"error": {code, message, hint}}`` with a status
chosen from the error's class.
"""
from __future__ import annotations

import json
import re
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request

from castlib.errors import AuthError, CastError, ConfigError, NotMedia, TVError, UpstreamError

MAX_BODY = 1 << 20
THUMB_LIMIT = 8 * 1024 * 1024
SHOW_CONTROLS = ("pause", "resume", "next", "prev", "stop")
_SOURCE = re.compile(r"^/api/sources/([A-Za-z0-9_-]+)(?:/(status|connect|disconnect|list|thumb))?(?:/(.+))?$")


class BadRequest(Exception):
    def __init__(self, message: str, code: str = "bad_request"):
        super().__init__(message)
        self.code = code


def status_for(err: CastError) -> int:
    if isinstance(err, AuthError):
        return 401
    if isinstance(err, NotMedia):
        return 404
    if isinstance(err, UpstreamError):
        return 502
    if isinstance(err, TVError):
        return 503
    if isinstance(err, ConfigError):
        return 400
    return 500


def dispatch(app, handler, path: str, query: str) -> None:
    try:
        _route(app, handler, handler.command, path, urllib.parse.parse_qs(query))
    except BadRequest as e:
        handler._drain()
        handler._json_error(400, e.code, str(e))
    except CastError as e:
        handler._drain()
        handler._json(status_for(e), {"error": e.as_dict()})
    except Exception as e:                       # never a traceback on the wire, never a hung connection
        traceback.print_exc(file=sys.stderr)
        handler._drain()
        handler._json_error(500, "internal", "cast-tv hit an internal error: %s" % e)


def _body(handler) -> dict:
    """The JSON object in a POST body (an empty body is ``{}``); marks the body consumed."""
    length = handler.headers.get("Content-Length", "")
    handler._drained = True
    if not length.isdigit():
        return {}
    n = int(length)
    if n > MAX_BODY:
        handler.close_connection = True
        raise BadRequest("The request body is too large.")
    raw = handler.rfile.read(n) if n else b""
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise BadRequest("The request body is not JSON.")
    if not isinstance(data, dict):
        raise BadRequest("The request body must be a JSON object.")
    return data


def _method(handler, method: str, allowed: tuple) -> bool:
    """False (after answering 405) when ``method`` is not one of ``allowed``; HEAD rides with GET."""
    if method == "HEAD":
        method = "GET"
    if method in allowed:
        return True
    handler._drain()
    handler._json(405, {"error": {"code": "method_not_allowed",
                                  "message": "Use %s here." % " or ".join(allowed),
                                  "hint": None}},
                  headers=[("Allow", ", ".join(allowed))])
    return False


def _route(app, handler, method: str, path: str, params: dict) -> None:
    path = path.rstrip("/") or "/api"
    if path == "/api/status":
        if _method(handler, method, ("GET",)):
            handler._drain()
            handler._json(200, app.status())
        return
    if path == "/api/tv/discover":
        if _method(handler, method, ("POST",)):
            _body(handler)
            handler._json(200, {"tvs": app.discover(), "tv": app.public_tv()})
        return
    if path == "/api/tv/select":
        if _method(handler, method, ("POST",)):
            body = _body(handler)
            handler._json(200, {"tv": app.select_tv(str(body.get("ip") or ""))})
        return
    if path == "/api/cast":
        if _method(handler, method, ("POST",)):
            body = _body(handler)
            item = app.resolve(_field(body, "source"), _field(body, "id"),
                               str(body.get("quality") or "auto"))
            cast = app.cast(item)
            handler._json(202, {"cast": cast.as_dict()})
        return
    if path == "/api/show":
        if _method(handler, method, ("POST",)):
            body = _body(handler)
            wanted = body.get("items")
            if not isinstance(wanted, list) or not wanted:
                raise BadRequest("Give a non-empty list of items.")
            items = [app.resolve(_field(entry, "source"), _field(entry, "id"),
                                 str(entry.get("quality") or "auto"))
                     for entry in wanted if isinstance(entry, dict)]
            interval = body.get("interval")
            show = app.show(items, interval)
            handler._json(202, {"show": show.as_dict()})
        return
    if path.startswith("/api/show/"):
        control = path[len("/api/show/"):]
        if control not in SHOW_CONTROLS:
            handler._drain()
            handler._json_error(404, "not_found", "Not found.")
            return
        if _method(handler, method, ("POST",)):
            _body(handler)
            show = app.show_now
            if show is None:
                raise ConfigError("no_show", "No slideshow is running.")
            getattr(show, control)()
            handler._json(200, {"show": show.as_dict()})
        return
    if path == "/api/stop":
        if _method(handler, method, ("POST",)):
            _body(handler)
            app.stop()
            handler._json(200, {"cast": app.current.as_dict() if app.current else None,
                                "show": None})
        return
    if path == "/api/errors":
        if _method(handler, method, ("GET",)):
            handler._drain()
            handler._json(200, {"errors": app.errors.list()})
        return
    if path == "/api/settings":
        if not _method(handler, method, ("GET", "POST")):
            return
        if method == "POST":
            body = _body(handler)
            if "interval" in body:
                app.set_interval(body["interval"])
        else:
            handler._drain()
        handler._json(200, {"settings": app.settings.as_dict()})
        return
    m = _SOURCE.match(path)
    if m:
        _source_route(app, handler, method, m.group(1), m.group(2), m.group(3), params)
        return
    handler._drain()
    handler._json_error(404, "not_found", "Not found.")


def _field(body: dict, name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str) or not value:
        raise BadRequest("Missing %r." % name)
    return value


def _source_route(app, handler, method, name, action, rest, params) -> None:
    if name == "local":
        handler._drain()
        handler._json_error(404, "not_found", "Not found.")   # CLI files are not browsable
        return
    src = app.source(name)
    if action == "thumb" and rest:
        if _method(handler, method, ("GET",)):
            handler._drain()
            _thumb(handler, src, urllib.parse.unquote(rest))
        return
    if rest is not None:
        handler._drain()
        handler._json_error(404, "not_found", "Not found.")
        return
    if action in (None, "status"):
        if _method(handler, method, ("GET",)):
            handler._drain()
            handler._json(200, src.status())
        return
    if action == "connect":
        if _method(handler, method, ("POST",)):
            body = _body(handler)
            handler._json(200, src.connect(**{k: v for k, v in body.items()
                                              if isinstance(k, str)}))
        return
    if action == "disconnect":
        if _method(handler, method, ("POST",)):
            _body(handler)
            src.disconnect()
            handler._json(200, src.status())
        return
    if action == "list":
        if _method(handler, method, ("GET",)):
            handler._drain()
            listing = src.list((params.get("path") or [None])[0], (params.get("page") or [None])[0])
            handler._json(200, listing.as_dict())
        return
    handler._drain()
    handler._json_error(404, "not_found", "Not found.")


def _thumb(handler, src, source_id: str) -> None:
    """Fetch the thumbnail through the source's fresh ``Upstream`` and hand the bytes over."""
    up = src.thumb(source_id)
    if up is None:
        handler._json_error(404, "not_found", "No thumbnail.")
        return
    req = urllib.request.Request(up.url, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*,*/*"})
    for k, v in up.headers.items():
        req.add_header(k, v)
    try:
        with (up.opener.open(req, timeout=20) if up.opener is not None
              else urllib.request.urlopen(req, timeout=20)) as resp:
            ctype = (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
            data = resp.read(THUMB_LIMIT + 1)
    except urllib.error.HTTPError as e:
        handler._json_error(502, "thumb_refused", "The source answered %d for the thumbnail." % e.code)
        return
    except Exception as e:
        handler._json_error(502, "thumb_failed", "Could not fetch the thumbnail: %s" % e)
        return
    if len(data) > THUMB_LIMIT:
        handler._json_error(502, "thumb_too_large", "The thumbnail is unreasonably large.")
        return
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "private, max-age=3600")
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(data)
