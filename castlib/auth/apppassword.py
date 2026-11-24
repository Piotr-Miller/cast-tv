"""One app-password credential, kept in ``config_dir()/<name>.json`` readable by this user only.

Unlike ``TokenStore`` there is nothing to refresh: the record is the server,
the login name, the user id, the app password and the account's display
name. A file missing any of the first four counts as absent.
"""
from __future__ import annotations

import json
import os
import threading

from castlib import config

FIELDS = ("server", "login", "user_id", "password", "account")
REQUIRED = ("server", "login", "user_id", "password")


class AppPasswordStore:
    """The credential of one source, in memory after the first read and on disk (mode 0600 on POSIX)."""

    def __init__(self, name: str):
        self.name = name
        self.path = os.path.join(config.config_dir(), name + ".json")
        self._lock = threading.Lock()
        self._data: dict | None = None
        self._loaded = False

    def _read(self) -> dict | None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or not all(isinstance(data.get(k), str) and data.get(k)
                                                 for k in REQUIRED):
            return None
        return {k: data.get(k) for k in FIELDS}

    def load(self) -> dict | None:
        """The stored record, or ``None``; read from disk once, then kept in memory."""
        with self._lock:
            if not self._loaded:
                self._data, self._loaded = self._read(), True
            return dict(self._data) if self._data else None

    def exists(self) -> bool:
        return self.load() is not None

    def save(self, record: dict) -> dict:
        data = {k: record.get(k) for k in FIELDS}
        with self._lock:
            config.write_private(self.path, json.dumps(data))
            self._data, self._loaded = data, True
            return dict(data)

    def clear(self) -> None:
        """Forget the credential in memory and on disk."""
        with self._lock:
            self._data, self._loaded = None, True
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
