"""What differs per operating system: firewall advice and staying awake.

Phase 3 ships the firewall hint and no-op stay-awake hooks; Phase 7 fills
the hooks with ``systemd-inhibit`` and ``SetThreadExecutionState``.
"""
from __future__ import annotations

import sys
import threading


def firewall_hint(port: int) -> str:
    """The one command that opens the media port on this platform."""
    if sys.platform == "win32":
        return ('netsh advfirewall firewall add rule name="cast-tv" dir=in action=allow '
                "protocol=TCP localport=%d" % port)
    return "sudo firewall-cmd --add-port=%d/tcp" % port


class StayAwake:
    """Keeps the machine from sleeping while something plays; counted, so nested use is safe."""

    def __init__(self):
        self._count = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self._count += 1

    def stop(self) -> None:
        with self._lock:
            if self._count > 0:
                self._count -= 1

    @property
    def active(self) -> bool:
        with self._lock:
            return self._count > 0
