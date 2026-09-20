#!/usr/bin/env python3
"""Log what the TV says about itself while something casts, once a second.

For the s11-screensaver measurement: run it next to a cast, note by hand the wall-clock
second the screen goes dark, then read back what any of these fields did at that moment.
Nothing here writes to the TV; every call is a read.

    python3 watch-tv.py 192.168.50.142 > run1.tsv

Columns: time, seconds since start, AVTransport state, position, /api/v2 PowerState,
the raw device dict's fields that ever change, and the RenderingControl mute/volume
(a cheap check of whether the TV answers at all while its saver is up).
"""
import json
import sys
import time
import urllib.request

TV = sys.argv[1] if len(sys.argv) > 1 else "192.168.50.142"
AVT = "urn:schemas-upnp-org:service:AVTransport:1"
RC = "urn:schemas-upnp-org:service:RenderingControl:1"
ENVELOPE = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            '<u:%s xmlns:u="%s">%s</u:%s></s:Body></s:Envelope>')


def soap(path, svc, action, body=""):
    data = (ENVELOPE % (action, svc, body, action)).encode()
    req = urllib.request.Request("http://%s:9197%s" % (TV, path), data=data, headers={
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPACTION": '"%s#%s"' % (svc, action)})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode("utf-8", "replace")


def tag(xml, name):
    a = xml.find("<%s>" % name)
    if a < 0:
        return ""
    b = xml.find("</%s>" % name, a)
    return xml[a + len(name) + 2:b]


def rest():
    try:
        with urllib.request.urlopen("http://%s:8001/api/v2/" % TV, timeout=5) as r:
            return json.load(r).get("device", {})
    except Exception as exc:
        return {"error": type(exc).__name__}


start = time.time()
print("time\tsecs\ttransport\tposition\tpower\tmute\tvolume\tnote")
sys.stdout.flush()
first_device = None
while True:
    now = time.time()
    try:
        ti = soap("/upnp/control/AVTransport1", AVT, "GetTransportInfo", "<InstanceID>0</InstanceID>")
        transport = tag(ti, "CurrentTransportState")
    except Exception as exc:
        transport = "ERR:%s" % type(exc).__name__
    try:
        pi = soap("/upnp/control/AVTransport1", AVT, "GetPositionInfo", "<InstanceID>0</InstanceID>")
        position = tag(pi, "RelTime")
    except Exception as exc:
        position = "ERR:%s" % type(exc).__name__
    try:
        mv = soap("/upnp/control/RenderingControl1", RC, "GetMute",
                  "<InstanceID>0</InstanceID><Channel>Master</Channel>")
        mute = tag(mv, "CurrentMute")
    except Exception as exc:
        mute = "ERR:%s" % type(exc).__name__
    try:
        vv = soap("/upnp/control/RenderingControl1", RC, "GetVolume",
                  "<InstanceID>0</InstanceID><Channel>Master</Channel>")
        volume = tag(vv, "CurrentVolume")
    except Exception as exc:
        volume = "ERR:%s" % type(exc).__name__
    device = rest()
    note = ""
    if first_device is None:
        first_device = device
    else:
        changed = [k for k in set(first_device) | set(device)
                   if first_device.get(k) != device.get(k)]
        if changed:
            note = "device changed: " + ",".join("%s=%s" % (k, device.get(k)) for k in sorted(changed))
    print("%s\t%d\t%s\t%s\t%s\t%s\t%s\t%s" % (
        time.strftime("%H:%M:%S"), int(now - start), transport, position,
        device.get("PowerState", "?"), mute, volume, note))
    sys.stdout.flush()
    time.sleep(max(0.0, 1.0 - (time.time() - now)))
