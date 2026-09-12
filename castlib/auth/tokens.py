"""One OAuth credential per source, kept in ``config_dir()/<name>.json`` readable by this user only.

The store holds the access token with its expiry, the refresh token, the
account it belongs to and the granted scope. ``get_access_token()`` hands out
the access token while it is good for another minute and refreshes it
otherwise, through the refresher the flow module provides; a caller that just
saw a 401 asks for a refresh on demand with ``force=True``.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable

from castlib import config
from castlib.errors import AuthError

REFRESH_MARGIN = 60.0        # seconds before expiry at which the token counts as stale
FIELDS = ("access_token", "expires_at", "refresh_token", "account", "scope")


class TokenStore:
    """The credential of one source, in memory and on disk (mode 0600)."""

    def __init__(self, name: str):
        self.name = name
        self.path = os.path.join(config.config_dir(), name + ".json")
        self._lock = threading.Lock()
        self._data: dict | None = None      # None until the first read
        self._loaded = False

    # ------------------------------------------------------------- storage
    def _read(self) -> dict | None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or not data.get("refresh_token"):
            return None
        return {k: data.get(k) for k in FIELDS}

    def _load_locked(self) -> dict | None:
        if not self._loaded:
            self._data = self._read()
            self._loaded = True
        return self._data

    def load(self) -> dict | None:
        """The stored credential, or ``None``; read from disk once, then kept in memory."""
        with self._lock:
            data = self._load_locked()
            return dict(data) if data else None

    def exists(self) -> bool:
        return self.load() is not None

    def account(self) -> dict | None:
        data = self.load()
        return (data or {}).get("account")

    def save(self, tokens: dict, account: dict | None = None, scope: str | None = None) -> dict:
        """Store a token response (``access_token``, ``expires_in``, ``refresh_token``); returns what was stored."""
        now = time.time()
        with self._lock:
            old = self._load_locked() or {}
            data = {
                "access_token": tokens.get("access_token"),
                "expires_at": now + float(tokens.get("expires_in") or 0),
                # a refresh answer may omit the refresh token: the old one stays valid
                "refresh_token": tokens.get("refresh_token") or old.get("refresh_token"),
                "account": account if account is not None else old.get("account"),
                "scope": scope or tokens.get("scope") or old.get("scope"),
            }
            config.write_private(self.path, json.dumps(data))
            self._data = data
            self._loaded = True
            return dict(data)

    def set_account(self, account: dict | None) -> None:
        with self._lock:
            data = self._load_locked()
            if data is None:
                return
            data["account"] = account
            config.write_private(self.path, json.dumps(data))

    def clear(self) -> None:
        """Forget the credential in memory and on disk."""
        with self._lock:
            self._data, self._loaded = None, True
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass

    # ------------------------------------------------------------- tokens
    def get_access_token(self, refresher: Callable[[str], dict], force: bool = False) -> str:
        """A usable access token: the stored one while it is fresh, else a refreshed one.

        ``refresher(refresh_token)`` returns the token endpoint's answer and
        raises ``AuthError`` when the refresh token is refused; the store then
        keeps the credential (the source decides what "expired" means) and the
        error propagates. ``force`` refreshes even a token that looks fresh: the
        server just refused it.
        """
        with self._lock:
            data = self._load_locked()
            if data is None:
                raise AuthError("no_token", "Not signed in.", source=self.name)
            token = data.get("access_token")
            fresh = token and (data.get("expires_at") or 0) - time.time() > REFRESH_MARGIN
            if fresh and not force:
                return token
            refresh_token = data.get("refresh_token")
            # the refresh runs under the lock: two handler threads that both hit
            # a stale token make one request, not two racing ones
            answer = refresher(refresh_token)
            data = {
                "access_token": answer.get("access_token"),
                "expires_at": time.time() + float(answer.get("expires_in") or 0),
                "refresh_token": answer.get("refresh_token") or refresh_token,
                "account": data.get("account"),
                "scope": answer.get("scope") or data.get("scope"),
            }
            config.write_private(self.path, json.dumps(data))
            self._data = data
            return data["access_token"]
