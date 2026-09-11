"""SOAP calls to the renderer's AVTransport service."""
from __future__ import annotations

import re
import urllib.request

AVT = "urn:schemas-upnp-org:service:AVTransport:1"
RC = "urn:schemas-upnp-org:service:RenderingControl:1"


def soap(url: str, svc: str, action: str, body: str = "") -> str:
    env = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
           ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
           '<u:{a} xmlns:u="{s}"><InstanceID>0</InstanceID>{b}</u:{a}>'
           "</s:Body></s:Envelope>").format(a=action, s=svc, b=body)
    req = urllib.request.Request(url, env.encode(), {
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPAction": '"%s#%s"' % (svc, action)})
    return urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")


def tag(xml: str, name: str) -> str:
    m = re.search(r"<%s>(.*?)</%s>" % (name, name), xml, re.S)
    return m.group(1) if m else ""


def transport_state(avt: str):
    """``(state, reltime, duration)`` as the TV reports them - RelTime is ``0:00:00``, not zero-padded."""
    info = soap(avt, AVT, "GetPositionInfo")
    state = tag(soap(avt, AVT, "GetTransportInfo"), "CurrentTransportState")
    return state, tag(info, "RelTime"), tag(info, "TrackDuration")
