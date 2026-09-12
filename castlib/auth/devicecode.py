"""The OAuth 2.0 device authorization grant against Microsoft Entra, in the standard library.

Chosen over auth code + PKCE because Entra only accepts ``http://localhost``
redirects for public clients, so a sign-in started from the phone could never
land its redirect. Device code has no redirect at all: ``start()`` asks for a
code, the user types it on any device, ``poll()`` waits for the token. The
five documented polling errors are handled by name; a refresh uses the same
token endpoint with ``grant_type=refresh_token``.

Reference: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from castlib.errors import AuthError, UpstreamError

AUTHORITY = "https://login.microsoftonline.com"
GRANT_DEVICE = "urn:ietf:params:oauth:grant-type:device_code"
SLOW_DOWN_STEP = 5.0         # seconds added to the interval on ``slow_down``
DEFAULT_INTERVAL = 5.0
DEFAULT_EXPIRES = 900.0
TIMEOUT = 30

FINAL_ERRORS = {
    "authorization_declined": "You declined the sign-in. Start again when you are ready.",
    "expired_token": "The code expired before it was entered. Start again for a new one.",
    "bad_verification_code": "That code was not recognised. Start again for a new one.",
}


def _post_form(url: str, data: dict, source: str = "onedrive") -> tuple[int, dict]:
    """POST a form and read a JSON answer; ``(status, body)``. Network trouble raises ``UpstreamError``."""
    body = urllib.parse.urlencode(data).encode("ascii")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            status, raw = r.status, r.read(1 << 20)
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read(1 << 20)
    except Exception as e:
        raise UpstreamError("login_unreachable", "Could not reach the Microsoft sign-in service: %s" % e,
                            source=source)
    try:
        parsed = json.loads(raw.decode("utf-8", "replace")) if raw.strip() else {}
    except ValueError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return status, parsed


def _endpoint(tenant: str, leaf: str) -> str:
    return "%s/%s/oauth2/v2.0/%s" % (AUTHORITY, tenant, leaf)


def start(client_id: str, scopes: str, tenant: str = "consumers") -> dict:
    """Ask for a device code: ``{user_code, verification_uri, expires_in, interval, message, device_code}``."""
    status, data = _post_form(_endpoint(tenant, "devicecode"),
                              {"client_id": client_id, "scope": scopes})
    if status >= 400 or not data.get("device_code") or not data.get("user_code"):
        raise UpstreamError(
            "devicecode_refused",
            "Microsoft did not issue a sign-in code (%d): %s" % (
                status, data.get("error_description") or data.get("error") or "no detail"),
            hint="Check the app registration: personal accounts allowed, "
                 "\"Allow public client flows\" set to Yes.",
            source="onedrive")
    return {
        "user_code": str(data["user_code"]),
        "verification_uri": str(data.get("verification_uri") or "https://microsoft.com/devicelogin"),
        "expires_in": float(data.get("expires_in") or DEFAULT_EXPIRES),
        "interval": float(data.get("interval") or DEFAULT_INTERVAL),
        "message": str(data.get("message") or ""),
        "device_code": str(data["device_code"]),
    }


def poll(client_id: str, flow: dict, tenant: str = "consumers",
         stop: threading.Event | None = None) -> dict:
    """Wait for the user to finish; returns the token answer or raises ``AuthError``.

    ``authorization_pending`` keeps polling at ``interval``; ``slow_down``
    adds five seconds; ``authorization_declined``, ``expired_token`` and
    ``bad_verification_code`` end the flow. The flow also ends locally when
    ``expires_in`` runs out, and quietly (``AuthError("cancelled")``) when
    ``stop`` is set.
    """
    stop = stop or threading.Event()
    interval = float(flow.get("interval") or DEFAULT_INTERVAL)
    deadline = time.monotonic() + float(flow.get("expires_in") or DEFAULT_EXPIRES)
    url = _endpoint(tenant, "token")
    while True:
        if stop.wait(interval):
            raise AuthError("cancelled", "Sign-in cancelled.", source="onedrive")
        if time.monotonic() > deadline:
            raise AuthError("expired_token", FINAL_ERRORS["expired_token"], source="onedrive")
        status, data = _post_form(url, {"grant_type": GRANT_DEVICE, "client_id": client_id,
                                        "device_code": flow["device_code"]})
        if status == 200 and data.get("access_token"):
            return data
        error = str(data.get("error") or "")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += SLOW_DOWN_STEP
            continue
        if error in FINAL_ERRORS:
            raise AuthError(error, FINAL_ERRORS[error], source="onedrive")
        raise UpstreamError("token_refused", "Microsoft answered %d during sign-in: %s" % (
            status, data.get("error_description") or error or "no detail"), source="onedrive")


def refresh(client_id: str, refresh_token: str, scopes: str, tenant: str = "consumers") -> dict:
    """A fresh access token for a stored refresh token; ``invalid_grant`` means the sign-in is over."""
    if not refresh_token:
        raise AuthError("no_token", "Not signed in.", source="onedrive")
    status, data = _post_form(_endpoint(tenant, "token"), {
        "grant_type": "refresh_token", "client_id": client_id,
        "refresh_token": refresh_token, "scope": scopes})
    if status == 200 and data.get("access_token"):
        return data
    error = str(data.get("error") or "")
    if error in ("invalid_grant", "interaction_required", "invalid_client", "unauthorized_client"):
        raise AuthError("refresh_rejected",
                        "The OneDrive sign-in is no longer valid (%s). Connect again." % error,
                        hint=str(data.get("error_description") or "")[:200] or None,
                        source="onedrive")
    raise UpstreamError("refresh_failed", "Microsoft answered %d on token refresh: %s" % (
        status, data.get("error_description") or error or "no detail"), source="onedrive")
