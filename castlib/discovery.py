"""Finding the TV: SSDP discovery, control URLs, and this machine's addresses.

M-SEARCH leaves from every LAN interface, not from whichever one the routing
table prefers: a Windows machine typically carries Wi-Fi, Ethernet, Hyper-V,
WSL and VPN adapters, and a search sent through the wrong one finds nothing.
Each interface's answers are counted, so "no TV found" can say where it looked.
"""
from __future__ import annotations

import ipaddress
import re
import select
import socket
import sys
import time
import urllib.parse
import urllib.request
from xml.sax.saxutils import unescape

from castlib.dlna import AVT, RC

SSDP_ADDR, SSDP_PORT = "239.255.255.250", 1900
# the one socket constructor and select() discovery uses: tests replace these module
# attributes, never ``socket.socket`` or ``select.select``, which every thread shares
_new_socket = socket.socket
_select = select.select


MSEARCH = ("M-SEARCH * HTTP/1.1\r\nHOST:%s:%d\r\nMAN:\"ssdp:discover\"\r\n"
           "MX:2\r\nST:urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n"
           % (SSDP_ADDR, SSDP_PORT)).encode()


def lan_interfaces() -> list[tuple[str, str]]:
    """``[(adapter name, ipv4)]`` M-SEARCH can leave from: loopback and link-local skipped."""
    try:
        import ifaddr
    except ImportError:
        return []
    out = []
    for adapter in ifaddr.get_adapters():
        for ip in adapter.ips:
            if not isinstance(ip.ip, str):
                continue                        # IPv6: SSDP here is IPv4
            try:
                addr = ipaddress.IPv4Address(ip.ip)
            except ValueError:
                continue
            if addr.is_loopback or addr.is_link_local:
                continue
            out.append((adapter.nice_name or adapter.name, ip.ip))
    return out


def _msearch_socket(ip: str | None, platform: str | None = None) -> socket.socket:
    """A UDP socket whose multicast leaves through ``ip`` (the routing table's choice when ``None``)."""
    s = _new_socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if (platform or sys.platform) != "win32":
            # on Windows SO_REUSEADDR lets another socket take the port over, not share it
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if ip is not None:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
            s.bind((ip, 0))
        s.setblocking(False)
    except OSError:
        s.close()
        raise
    return s


def msearch(timeout=4, interfaces=None, platform=None):
    """Send M-SEARCH from each interface and collect the answers until ``timeout``.

    Returns ``(locations, report)``: ``{renderer ip: description url}`` over
    all interfaces, and ``[{name, ip, responses[, error]}]`` with the number of
    distinct devices that answered on each. With no interface enumerated, one
    socket goes out the default route, as before.
    """
    ifaces = lan_interfaces() if interfaces is None else list(interfaces)
    if not ifaces:
        ifaces = [("default route", None)]
    socks, report = {}, []
    for name, ip in ifaces:
        entry = {"name": name, "ip": ip, "responses": 0}
        report.append(entry)
        try:
            s = _msearch_socket(ip, platform)
        except OSError as e:
            entry["error"] = str(e)
            continue
        try:
            s.sendto(MSEARCH, (SSDP_ADDR, SSDP_PORT))
        except OSError as e:                    # an adapter that is down, or has no route
            entry["error"] = str(e)
            s.close()
            continue
        socks[s] = (entry, set())
    found = {}
    deadline = time.monotonic() + timeout
    try:
        while socks:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            ready, _, _ = _select(list(socks), [], [], left)
            for s in ready:
                try:
                    data, addr = s.recvfrom(65507)
                except OSError:
                    continue
                m = re.search(r"(?i)^location:\s*(\S+)", data.decode("utf-8", "replace"), re.M)
                if not m:
                    continue
                entry, seen = socks[s]
                if addr[0] not in seen:
                    seen.add(addr[0])
                    entry["responses"] += 1
                found.setdefault(addr[0], m.group(1))
    finally:
        for s in socks:
            s.close()
    return found, report


def discover(timeout=4, report=None):
    """Return [(ip, control_url, friendly_name)] for renderers on the network.

    ``report``, when a list, receives the per-interface answer counts (see ``msearch``).
    """
    found, searched = msearch(timeout)
    if report is not None:
        report.extend(searched)
    out = []
    for ip, loc in found.items():
        try:
            xml = urllib.request.urlopen(loc, timeout=3).read().decode("utf-8", "replace")
        except Exception:
            continue
        ctrl = service_control_url(xml, AVT)
        if ctrl:
            name = re.search(r"<friendlyName>(.*?)</friendlyName>", xml, re.S)
            out.append((ip, urllib.parse.urljoin(loc, ctrl),
                        unescape(name.group(1), {"&quot;": '"', "&apos;": "'"})
                        if name else ip))
    return out


def service_control_url(xml, svc_type):
    for blob in re.findall(r"<service>(.*?)</service>", xml, re.S):
        if svc_type in blob:
            m = re.search(r"<controlURL>(.*?)</controlURL>", blob, re.S)
            if m:
                return m.group(1).strip()
    return None


def control_urls(ip):
    """Control endpoints for the TV's AVTransport and RenderingControl."""
    for port, path in ((9197, "/dmr"), (7676, "/dmr"), (9197, "/"), (52235, "/dmr")):
        loc = "http://%s:%d%s" % (ip, port, path)
        try:
            xml = urllib.request.urlopen(loc, timeout=3).read().decode("utf-8", "replace")
        except Exception:
            continue
        avt = service_control_url(xml, AVT)
        if avt:
            return (urllib.parse.urljoin(loc, avt),
                    urllib.parse.urljoin(loc, service_control_url(xml, RC) or ""))
    return None, None


def renderer_name(ip):
    """The ``friendlyName`` from the device description at ``ip``, or ``None``."""
    for port, path in ((9197, "/dmr"), (7676, "/dmr"), (9197, "/"), (52235, "/dmr")):
        try:
            xml = urllib.request.urlopen("http://%s:%d%s" % (ip, port, path),
                                         timeout=3).read().decode("utf-8", "replace")
        except Exception:
            continue
        m = re.search(r"<friendlyName>(.*?)</friendlyName>", xml, re.S)
        if m:
            return unescape(m.group(1), {"&quot;": '"', "&apos;": "'"})
    return None


def local_ip(target):
    """The address of the interface that routes to ``target``; no packet is sent."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((target, 9197))
    ip = s.getsockname()[0]
    s.close()
    return ip


def interface_addresses() -> set[str]:
    """Every IPv4 address configured on this machine's interfaces, loopback included.

    Uses ``ifaddr`` when installed (Phase 7 makes it a dependency, for
    Windows); otherwise asks the kernel per interface over ``SIOCGIFADDR``,
    which is Linux-only and needs no dependency.
    """
    addrs: set[str] = set()
    try:
        import ifaddr
    except ImportError:
        ifaddr = None
    if ifaddr is not None:
        for adapter in ifaddr.get_adapters():
            for ip in adapter.ips:
                if isinstance(ip.ip, str):
                    addrs.add(ip.ip)
        return addrs
    if sys.platform.startswith("linux"):
        import fcntl
        import struct
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for _index, name in socket.if_nameindex():
                try:
                    res = fcntl.ioctl(s.fileno(), 0x8915,   # SIOCGIFADDR
                                      struct.pack("256s", name.encode()[:15]))
                except OSError:
                    continue                # no IPv4 on this interface
                addrs.add(socket.inet_ntoa(res[20:24]))
        finally:
            s.close()
    return addrs


def local_addresses() -> set[str]:
    """Names and IPv4 addresses a browser may put in ``Host`` when it means this machine.

    Loopback, every interface address, everything the hostname resolves to and
    the address on the default route.
    """
    addrs = {"localhost", "127.0.0.1", "::1"}
    try:
        addrs |= interface_addresses()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    try:
        addrs.add(local_ip("192.0.2.1"))
    except OSError:
        pass
    return addrs
