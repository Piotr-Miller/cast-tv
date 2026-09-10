"""Finding the TV: SSDP discovery, control URLs, and this machine's addresses."""
from __future__ import annotations

import re
import socket
import time
import urllib.parse
import urllib.request
from xml.sax.saxutils import unescape

from castlib.dlna import AVT, RC

SSDP_ADDR, SSDP_PORT = "239.255.255.250", 1900


def discover(timeout=4):
    """Return [(ip, control_url, friendly_name)] for renderers on the network."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST:%s:%d\r\nMAN:\"ssdp:discover\"\r\n"
           "MX:2\r\nST:urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n"
           % (SSDP_ADDR, SSDP_PORT)).encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.settimeout(timeout)
    s.sendto(msg, (SSDP_ADDR, SSDP_PORT))
    found, deadline = {}, time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = s.recvfrom(65507)
        except socket.timeout:
            break
        m = re.search(r"(?i)^location:\s*(\S+)", data.decode("utf-8", "replace"), re.M)
        if m and addr[0] not in found:
            found[addr[0]] = m.group(1)
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


def local_ip(target):
    """The address of the interface that routes to ``target``; no packet is sent."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((target, 9197))
    ip = s.getsockname()[0]
    s.close()
    return ip


def local_addresses() -> set[str]:
    """Names and IPv4 addresses a browser may put in ``Host`` when it means this machine.

    Loopback plus every address the hostname resolves to and the one on the
    default route. Phase 7 enumerates interfaces properly.
    """
    addrs = {"localhost", "127.0.0.1", "::1"}
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
