"""Failures the CLI prints and the server renders.

Every ``die()`` message the scripts used to print survives here as the
``message`` of an exception, so the user sees the same text whether it lands on
stderr or in a JSON body.
"""
from __future__ import annotations

import time


class CastError(Exception):
    """A user-facing failure: a short ``code`` for the API, a ``message`` for people."""

    def __init__(self, code: str, message: str, hint: str | None = None,
                 source: str | None = None, item: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.source = source
        self.item = item
        self.at = time.time()

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "hint": self.hint,
                "source": self.source, "item": self.item, "at": self.at}

    def __str__(self) -> str:
        return self.message


class AuthError(CastError):
    """The source needs reconnecting: no token, an expired one, or a refused login."""


class UpstreamError(CastError):
    """Talking to a cloud failed: network trouble or an HTTP error from it."""


class NotMedia(CastError):
    """The address or item resolved, but nothing castable is behind it."""


class TVError(CastError):
    """The renderer refused, vanished, or never fetched a byte."""


class ConfigError(CastError):
    """Local state is unusable: a cookie jar, a cache entry, a bad name."""
