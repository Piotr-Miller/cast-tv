"""Nextcloud Login Flow v2 and the app-password calls, in the standard library, with no state.

The owner types the server address; ``start()`` asks the server for a login
page and a poll endpoint, the owner opens the page on any device and grants
access, and ``poll()`` receives cast-tv's own app password - once, as the
server hands it out only once. ``user()`` reads the account's user id (the
WebDAV root is named by it, not by the login name) and ``revoke()`` deletes
the app password on the server.

Every URL that carries or receives the password must have the canonical
base's scheme, host and port (``same_origin``); calls that carry it never
follow a redirect. No message carries a response body or a header.

Reference: https://docs.nextcloud.com/server/latest/developer_manual/client_apis/LoginFlow/index.html
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from castlib.errors import AuthError, CastError, ConfigError, UpstreamError
from castlib.net import NO_REDIRECT, _origin

SOURCE = "nextcloud"
SCHEMES = ("https",)            # tests add "http" for the scripted server on localhost
USER_AGENT = "cast-tv"          # the server may name the app password after it
POLL_INTERVAL = 2.0
FLOW_LIFETIME = 20 * 60.0       # "The token will be valid for 20 minutes."
TIMEOUT = 30
JSON_LIMIT = 1 << 20
HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?|\[[0-9A-Fa-f:.]{2,45}\]")


@dataclass(frozen=True)
class Base:
    """The one canonical server address: ``(scheme, host, effective port)`` plus a path without a trailing ``/``."""
    scheme: str
    host: str
    port: int
    path: str = ""

    @property
    def origin(self) -> tuple:
        return self.scheme, self.host.lower().strip("[]"), self.port

    @property
    def url(self) -> str:
        default = {"http": 80, "https": 443}.get(self.scheme)
        netloc = self.host if self.port == default else "%s:%d" % (self.host, self.port)
        return "%s://%s%s" % (self.scheme, netloc, self.path)


def _refuse(message: str) -> ConfigError:
    return ConfigError("bad_address", message, source=SOURCE)


def normalise(address) -> Base:
    """The canonical base for what the owner typed; ``ConfigError`` says why an address is refused."""
    text = address.strip() if isinstance(address, str) else ""
    if not text:
        raise _refuse("Type the address of your Nextcloud server, for example cloud.example.com.")
    if any(ord(c) < 33 or ord(c) == 127 for c in text):
        raise _refuse("A server address cannot contain spaces or control characters.")
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        raise _refuse("That is not a server address cast-tv can read.") from None
    scheme = parts.scheme.lower()
    if scheme not in SCHEMES:
        if scheme == "http":
            raise ConfigError("http_refused",
                              "cast-tv only connects to Nextcloud over HTTPS: the app password "
                              "would travel unencrypted over http://.", source=SOURCE)
        raise _refuse("A Nextcloud address starts with https://.")
    if "@" in parts.netloc:
        raise _refuse("Type the address without a user name (nothing before an @); "
                      "you sign in on the server's own page.")
    if parts.query or parts.fragment or text.endswith(("?", "#")):
        raise _refuse("Type only the server address, without ? or #.")
    host = parts.netloc.rsplit(":", 1)[0] if not parts.netloc.endswith("]") else parts.netloc
    try:
        port = parts.port
    except ValueError:
        raise _refuse("The port in that address is not a number between 1 and 65535.") from None
    if not HOST_RE.fullmatch(host or "") or ".." in host or port == 0:
        raise _refuse("That is not a server address cast-tv can read.")
    default = {"http": 80, "https": 443}[scheme]
    path = parts.path.rstrip("/")
    if any(seg in (".", "..") for seg in path.split("/")):
        raise _refuse("That is not a server address cast-tv can read.")
    return Base(scheme, host.lower(), port or default, path)


def same_origin(base: Base, url) -> bool:
    """Whether ``url`` has the base's scheme, host and effective port (a relative or ``//`` URL never does)."""
    if not isinstance(url, str) or "://" not in url:
        return False
    authority = re.split(r"[/?#]", url.split("://", 1)[1], maxsplit=1)[0]
    if re.search(r"[\\@\s\x00-\x1f\x7f]", authority):
        return False                             # a browser reads "a\@b" as host a; urlsplit reads b
    origin = _origin(url)
    if origin is None:
        return False
    scheme, host, port = origin
    return (scheme, host.strip("[]"), port) == base.origin


def basic(login: str, password: str) -> str:
    """The ``Authorization`` value for an app password."""
    return "Basic " + base64.b64encode(("%s:%s" % (login, password)).encode("utf-8")).decode("ascii")


def call(method: str, url: str, headers: dict | None = None, body: bytes | None = None,
         limit: int = JSON_LIMIT) -> tuple[int, bytes]:
    """One request that never follows a redirect; ``(status, at most limit bytes)``.

    An HTTP error is an answer; anything that stops one arriving raises
    ``UpstreamError`` with no body, header or URL query in its message.
    """
    req = urllib.request.Request(url, data=body, method=method, headers=dict(
        {"User-Agent": USER_AGENT}, **(headers or {})))
    try:
        with NO_REDIRECT.open(req, timeout=TIMEOUT) as r:     # a 3xx would carry the password elsewhere
            return r.status, r.read(limit)
    except urllib.error.HTTPError as e:
        try:
            data = e.read(limit)
        except Exception:
            data = b""
        return e.code, data
    except CastError:
        raise
    except Exception as e:
        reason = getattr(e, "reason", None) or e.__class__.__name__
        raise UpstreamError("nextcloud_unreachable",
                            "Could not reach the Nextcloud server (%s)." % str(reason)[:120],
                            source=SOURCE) from None


def _json(data: bytes) -> dict:
    try:
        parsed = json.loads(data.decode("utf-8", "replace")) if data.strip() else {}
    except ValueError:
        parsed = None
    return parsed if isinstance(parsed, dict) else {}


def _unexpected(status: int, what: str) -> UpstreamError:
    return UpstreamError("nextcloud_http", "The Nextcloud server answered %d %s." % (status, what),
                         source=SOURCE)


def start(base: Base) -> dict:
    """Begin a login: ``{login, endpoint, token, expires_at, base}``; both URLs must be same-origin."""
    status, data = call("POST", base.url + "/index.php/login/v2", {"Accept": "application/json"}, b"")
    if status != 200:
        raise _unexpected(status, "when cast-tv asked to sign in; is this a Nextcloud server?")
    answer = _json(data)
    poll_part = answer.get("poll") if isinstance(answer.get("poll"), dict) else {}
    login, endpoint, token = answer.get("login"), poll_part.get("endpoint"), poll_part.get("token")
    if not (isinstance(login, str) and isinstance(endpoint, str) and isinstance(token, str) and token):
        raise UpstreamError("nextcloud_flow", "The server's sign-in answer is not a Nextcloud Login Flow.",
                            source=SOURCE)
    if not same_origin(base, login) or not same_origin(base, endpoint):
        raise UpstreamError("nextcloud_origin",
                            "The server sent a sign-in address on another host or port than %s; "
                            "cast-tv does not follow it." % base.url, source=SOURCE)
    return {"login": login, "endpoint": endpoint, "token": token,
            "expires_at": time.time() + FLOW_LIFETIME, "base": base}


def poll(flow: dict, stop: threading.Event | None = None) -> dict:
    """Wait for the owner to grant access: ``{server, loginName, appPassword}``.

    A 404 means "not yet"; the poll repeats every ``POLL_INTERVAL`` until
    ``FLOW_LIFETIME`` runs out (``AuthError("flow_expired")``) or ``stop`` is
    set (``AuthError("cancelled")``). Network trouble is retried until then.
    """
    stop = stop or threading.Event()
    base: Base = flow["base"]
    deadline = time.monotonic() + max(0.0, flow["expires_at"] - time.time())
    body = urllib.parse.urlencode({"token": flow["token"]}).encode("ascii")
    while True:
        if stop.wait(POLL_INTERVAL):
            raise AuthError("cancelled", "Sign-in cancelled.", source=SOURCE)
        if time.monotonic() > deadline:
            raise AuthError("flow_expired", "The sign-in link expired before access was granted. "
                            "Press Connect for a new one.", source=SOURCE)
        try:
            status, data = call("POST", flow["endpoint"], {
                "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, body)
        except UpstreamError:
            continue
        if status == 404:
            continue
        if status != 200:
            raise _unexpected(status, "while cast-tv waited for the sign-in")
        answer = _json(data)
        login, password = answer.get("loginName"), answer.get("appPassword")
        if not (isinstance(login, str) and login and isinstance(password, str) and password):
            raise UpstreamError("nextcloud_flow", "The server's sign-in answer carried no app password.",
                                source=SOURCE)
        if not same_origin(base, answer.get("server")):
            raise UpstreamError("nextcloud_origin",
                                "The server granted access for another host or port than %s; "
                                "cast-tv does not use it." % base.url, source=SOURCE)
        return {"server": base.url, "loginName": login, "appPassword": password}


def _ocs_headers(login: str, password: str) -> dict:
    return {"Authorization": basic(login, password), "OCS-APIRequest": "true",
            "Accept": "application/json"}


def _unauthorized() -> AuthError:
    return AuthError("nextcloud_unauthorized",
                     "The Nextcloud server refused cast-tv's app password. Connect again.", source=SOURCE)


def user(base: Base, login: str, password: str) -> dict:
    """``{id, displayname}`` of the signed-in account (``/ocs/v2.php/cloud/user``)."""
    status, data = call("GET", base.url + "/ocs/v2.php/cloud/user?format=json", _ocs_headers(login, password))
    if status == 401:
        raise _unauthorized()
    if status != 200:
        raise _unexpected(status, "when cast-tv asked who is signed in")
    ocs = _json(data).get("ocs")
    info = ocs.get("data") if isinstance(ocs, dict) else None
    uid = info.get("id") if isinstance(info, dict) else None
    if not isinstance(uid, str) or not uid or any(ord(c) < 32 or c == "/" for c in uid):
        raise UpstreamError("nextcloud_user", "The server did not say which account signed in.", source=SOURCE)
    name = info.get("displayname") or info.get("display-name")
    return {"id": uid, "displayname": name if isinstance(name, str) and name else None}


def revoke(base: Base, login: str, password: str) -> None:
    """Delete the app password on the server; ``AuthError`` on 401, ``UpstreamError`` on anything else not 200."""
    status, _ = call("DELETE", base.url + "/ocs/v2.php/core/apppassword", _ocs_headers(login, password))
    if status == 401:
        raise _unauthorized()
    if status != 200:
        raise _unexpected(status, "when cast-tv asked it to remove its app password")
