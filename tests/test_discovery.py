import re
import sys

import pytest

from castlib.discovery import interface_addresses, local_addresses


def _fib_trie_local_addresses():
    """IPv4 addresses the kernel lists as LOCAL: an independent source of truth on Linux."""
    try:
        with open("/proc/net/fib_trie", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    found = set()
    for prev, line in zip(lines, lines[1:]):
        if "/32 host LOCAL" in line:
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)", prev)
            if m:
                found.add(m.group(1))
    return found


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="fib_trie is Linux-only")
def test_allowed_hosts_cover_every_interface_address():
    kernel = _fib_trie_local_addresses()
    if not kernel:
        pytest.skip("no readable fib_trie")
    assert kernel <= interface_addresses()
    assert kernel <= local_addresses()


def test_local_addresses_always_include_loopback_names():
    assert {"localhost", "127.0.0.1", "::1"} <= local_addresses()
