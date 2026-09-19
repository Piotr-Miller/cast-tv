"""Google's OAuth 2.0 flow for desktop apps: a loopback redirect, PKCE, a refresh token.

The Picker scope is not on the closed list Google's device flow accepts
(research, 2026-09-08), so the consent runs once in a browser on the host:
``start()`` binds ``127.0.0.1:<random>``, builds the consent URL with PKCE
S256 and a ``state``, and waits for the browser to land the redirect; the
code is then exchanged for tokens with ``client_secret`` and the verifier.
The spike in the change folder proved this end to end on 2026-09-09.

The consent page must be opened on the machine running cast-tv: the
redirect goes to that machine's loopback and nowhere else. A phone that opens
the URL sees Google's page but the redirect lands nowhere; the UI says so.

The client comes, in this order, from the file ``GOOGLE_CLIENT_JSON`` names,
from ``config_dir()/google-client.json`` when it exists (either is the
``client_secret_*.json`` the Cloud console offers for a *Desktop app* client),
or from the one a release build carries (``_builtin_client``). Google's own docs
say an installed app cannot keep the secret confidential; it is never logged.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from castlib import config
from castlib.errors import AuthError, ConfigError, UpstreamError
from castlib.net import NO_REDIRECT

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
CLIENT_FILE = "google-client.json"
CONSENT_TIMEOUT = 300.0        # seconds the loopback waits for the browser
TIMEOUT = 30
HOW_TO_GET_A_CLIENT = (
    "The cast-tv downloads on GitHub Releases carry one. A source install can use its own "
    "Google Cloud client of type \"Desktop app\" (Photos Picker API enabled): point "
    "GOOGLE_CLIENT_JSON at its JSON, or save it as %s.")

PAGE_DONE = ("<!doctype html><meta charset=utf-8><title>cast-tv</title>"
             "<body style=\"font-family:sans-serif;padding:40px\">"
             "<h2>Google Photos is connected.</h2><p>You can close this tab and go back to cast-tv.</p>")
PAGE_FAIL = ("<!doctype html><meta charset=utf-8><title>cast-tv</title>"
             "<body style=\"font-family:sans-serif;padding:40px\">"
             "<h2>That did not work.</h2><p>%s</p>")

open_browser = webbrowser.open      # replaced in tests; ``False`` is not an error


def builtin_client() -> dict | None:
    """The client a release build wrote into ``_builtin_client``; ``None`` in a source tree."""
    from castlib.auth import _builtin_client as b
    cid, secret = getattr(b, "CLIENT_ID", None), getattr(b, "CLIENT_SECRET", None)
    if isinstance(cid, str) and cid and isinstance(secret, str) and secret:
        return {"client_id": cid, "client_secret": secret}
    return None                                 # half filled counts as none


def client_source() -> str | None:
    """Where the client comes from: an override file's path, ``"built-in"``, or ``None``."""
    env = os.environ.get("GOOGLE_CLIENT_JSON")
    if env:
        return env                              # named explicitly: used even if it is missing
    path = os.path.join(config.config_dir(), CLIENT_FILE)
    if os.path.exists(path):
        return path
    return "built-in" if builtin_client() else None


def load_client(path: str | None = None) -> dict:
    """``{client_id, client_secret}`` in the module's order; ``ConfigError`` when there is none or a file is odd."""
    hint = HOW_TO_GET_A_CLIENT % os.path.join(config.config_dir(), CLIENT_FILE)
    if path is None:
        path = client_source()
        if path == "built-in":
            return builtin_client()
        if path is None:
            raise ConfigError("no_google_client", "This copy of cast-tv has no Google client built in.",
                              hint=hint, source="gphotos")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise ConfigError("no_google_client", "The Google client file %s does not exist." % path,
                          hint=hint, source="gphotos")
    except (OSError, ValueError) as e:
        raise ConfigError("bad_google_client", "Could not read the Google client file %s: %s" % (path, e),
                          hint=hint, source="gphotos")
    if isinstance(data, dict) and "client_id" not in data:
        data = data.get("installed") or data.get("web") or {}   # the console wraps a Desktop client in "installed"
    cid = data.get("client_id") if isinstance(data, dict) else None
    secret = data.get("client_secret") if isinstance(data, dict) else None
    if not isinstance(cid, str) or not cid or not isinstance(secret, str):
        raise ConfigError("bad_google_client",
                          "%s does not look like a Desktop-app client file (no client_id/client_secret)." % path,
                          hint=hint, source="gphotos")
    return {"client_id": cid, "client_secret": secret}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _post_form(url: str, data: dict) -> tuple[int, dict]:
    body = urllib.parse.urlencode(data).encode("ascii")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with NO_REDIRECT.open(req, timeout=TIMEOUT) as r:     # a 3xx would carry the secret elsewhere
            status, raw = r.status, r.read(1 << 20)
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read(1 << 20)
    except Exception as e:
        raise UpstreamError("login_unreachable", "Could not reach Google's sign-in service: %s" % e,
                            source="gphotos")
    try:
        parsed = json.loads(raw.decode("utf-8", "replace")) if raw.strip() else {}
    except ValueError:
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        flow = self.server.flow
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        params = {k: v[0] for k, v in query.items()}
        if "code" not in params and "error" not in params:
            return self._page(404, PAGE_FAIL % "Nothing to do here.")    # a favicon, a stray tab
        problem = flow._land(params)
        if problem is None:
            self._page(200, PAGE_DONE)
        else:
            self._page(400, PAGE_FAIL % problem)

    def _page(self, status: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)


class Flow:
    """One consent round: a loopback listener, the consent URL, and the code it lands.

    ``auth_url`` is what the browser opens; ``wait()`` blocks for the
    redirect; ``exchange()`` turns the code into tokens; ``cancel()`` ends
    it early. The listener serves exactly one useful request and stops.
    """

    def __init__(self, client: dict, scopes: str, prompt: str | None = None):
        self.client = client
        self.scopes = scopes
        self.verifier = _b64url(secrets.token_bytes(48))
        self.state = secrets.token_urlsafe(16)
        self._done = threading.Event()
        self._landed: dict | None = None
        self._server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        self._server.flow = self
        self._server.timeout = 0.25
        self.port = self._server.server_address[1]
        self.redirect_uri = "http://127.0.0.1:%d/" % self.port
        challenge = _b64url(hashlib.sha256(self.verifier.encode("ascii")).digest())
        params = {"client_id": client["client_id"], "redirect_uri": self.redirect_uri,
                  "response_type": "code", "scope": scopes, "access_type": "offline",
                  "code_challenge": challenge, "code_challenge_method": "S256", "state": self.state}
        if prompt:
            params["prompt"] = prompt
        self.auth_url = AUTH + "?" + urllib.parse.urlencode(params)
        self._thread = threading.Thread(target=self._serve, name="google-loopback", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            while not self._done.is_set():
                self._server.handle_request()
        finally:
            self._server.server_close()

    def _land(self, params: dict) -> str | None:
        """The browser arrived; returns the text of what went wrong, or ``None`` when the code is good."""
        if params.get("state") != self.state:
            return "The redirect did not belong to this sign-in (state mismatch). Start again."
        if "error" in params:
            self._landed = {"error": params["error"]}
            self._done.set()
            return "Google answered: %s." % params["error"]
        self._landed = {"code": params["code"]}
        self._done.set()
        return None

    def wait(self, timeout: float = CONSENT_TIMEOUT) -> str:
        """The authorisation code, or ``AuthError`` on timeout, refusal or cancel."""
        if not self._done.wait(timeout):
            self.cancel()
            raise AuthError("consent_timeout",
                            "No consent arrived within %d minutes. Connect again when you are at this computer."
                            % round(timeout / 60), source="gphotos")
        landed = self._landed or {}
        if "code" in landed:
            return landed["code"]
        if landed.get("error") == "access_denied":
            raise AuthError("consent_declined", "You declined the Google consent. Connect again when you are ready.",
                            source="gphotos")
        if "error" in landed:
            raise AuthError("consent_failed", "Google answered %s on the consent page." % landed["error"],
                            source="gphotos")
        raise AuthError("cancelled", "Sign-in cancelled.", source="gphotos")

    def cancel(self) -> None:
        self._done.set()

    def exchange(self, code: str) -> dict:
        """Trade the code for tokens; the answer is Google's token JSON (``refresh_token`` may be absent)."""
        status, data = _post_form(TOKEN, {
            "code": code, "client_id": self.client["client_id"],
            "client_secret": self.client["client_secret"], "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code", "code_verifier": self.verifier})
        if status == 200 and data.get("access_token"):
            return data
        raise UpstreamError("token_refused", "Google answered %d when exchanging the consent code: %s" % (
            status, data.get("error_description") or data.get("error") or "no detail"), source="gphotos")


def start(client: dict, scopes: str, prompt: str | None = None, browser: bool = True) -> Flow:
    """Bind the loopback, build the consent URL and open the browser on this machine."""
    flow = Flow(client, scopes, prompt=prompt)
    if browser:
        try:
            open_browser(flow.auth_url)
        except Exception:
            pass                                 # the URL is shown for copying anyway
    return flow


def refresh(client: dict, refresh_token: str) -> dict:
    """A fresh access token; ``invalid_grant`` means the consent was revoked or the token is dead."""
    if not refresh_token:
        raise AuthError("no_token", "Not signed in.", source="gphotos")
    status, data = _post_form(TOKEN, {
        "grant_type": "refresh_token", "client_id": client["client_id"],
        "client_secret": client["client_secret"], "refresh_token": refresh_token})
    if status == 200 and data.get("access_token"):
        return data
    error = str(data.get("error") or "")
    if error in ("invalid_grant", "invalid_client", "unauthorized_client"):
        raise AuthError("refresh_rejected",
                        "The Google Photos consent is no longer valid (%s). Connect again." % error,
                        hint=str(data.get("error_description") or "")[:200] or None, source="gphotos")
    raise UpstreamError("refresh_failed", "Google answered %d on token refresh: %s" % (
        status, data.get("error_description") or error or "no detail"), source="gphotos")
