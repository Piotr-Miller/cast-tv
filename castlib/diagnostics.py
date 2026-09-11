"""What ``ffprobe`` can say about a file the TV refused, or is about to refuse.

Both functions return their findings instead of printing them, so the CLI
can print and the supervisor can attach them to an error. ``ffprobe`` is
optional: without it both answer with nothing.
"""
from __future__ import annotations

import json
import os
import subprocess

UNDECODED_AUDIO = ("dts", "truehd", "mlp")


def explain_failure(source: str) -> tuple[str | None, list[str]]:
    """``(media line, reasons)`` for a video the TV never started playing."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height,bit_rate",
             "-of", "json", source],
            capture_output=True, text=True, timeout=90).stdout
        streams = json.loads(out).get("streams", [])
    except Exception:
        return None, []
    media, reasons = None, []
    for st in streams:
        if st.get("codec_type") == "video":
            w, h = st.get("width") or 0, st.get("height") or 0
            mbit = int(st.get("bit_rate") or 0) / 1e6
            media = "%s %dx%d%s" % (st.get("codec_name", "?"), w, h,
                                    ", %.0f Mbit/s" % mbit if mbit else "")
            if mbit > 60:
                reasons.append("%.0f Mbit/s - DLNA players usually top out near 60" % mbit)
            if h and w and abs(w / h - 16 / 9) > 0.35:
                reasons.append("unusual %dx%d aspect (TVs expect something near 16:9)"
                               % (w, h))
        elif st.get("codec_type") == "audio" and st.get("codec_name") in UNDECODED_AUDIO:
            reasons.append("%s audio - Samsung does not decode it" % st["codec_name"])
        elif st.get("codec_type") == "data":
            reasons.append("extra data track (%s)" % st.get("codec_name", "?"))
    return media, reasons


def check_codecs(path: str) -> tuple[list[str], str | None]:
    """``(undecodable audio codecs, the ffmpeg command that fixes them)`` for a local file."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "stream=codec_type,codec_name", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return [], None
    bad = [l.split(",")[1] for l in out.strip().splitlines()
           if l.startswith("audio") and "," in l and l.split(",")[1] in UNDECODED_AUDIO]
    if not bad:
        return [], None
    return bad, 'ffmpeg -i "%s" -c:v copy -c:a eac3 -b:a 640k "%s"' % (
        path, os.path.splitext(path)[0] + ".eac3.mkv")
