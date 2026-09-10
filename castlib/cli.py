"""The three commands, reassembled on the registry-backed server.

``cast-tv`` binds first, registers the item (and its subtitle) under opaque
ids, hands the tokenised URL to the TV and runs the poll loop with the
constraints history hardened: RelTime arrives as ``0:00:00``, ``started``
latches on PLAYING/PAUSED_PLAYBACK only, TRANSITIONING gets a longer budget.
``cast-gopro`` and ``cast-photos`` resolve in process and call ``cast()``
directly instead of spawning a second server.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape

from castlib import config, net
from castlib.discovery import control_urls, discover, local_ip
from castlib.dlna import AVT, soap, tag
from castlib.errors import CastError
from castlib.items import MediaItem, Upstream
from castlib.media import MIME, didl, is_allowed_photo, kind_of_extension
from castlib.server import Server
from castlib.sources import gopro, sharelink

DEFAULT_PORT = 8895


# ------------------------------------------------------------ diagnostics
def explain_failure(source):
    """After the TV refuses to start: what about this file it may have rejected."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height,bit_rate",
             "-of", "json", source],
            capture_output=True, text=True, timeout=90).stdout
        streams = json.loads(out).get("streams", [])
    except Exception:
        return
    reasons = []
    for st in streams:
        if st.get("codec_type") == "video":
            w, h = st.get("width") or 0, st.get("height") or 0
            mbit = int(st.get("bit_rate") or 0) / 1e6
            print("   media: %s %dx%d%s" % (
                st.get("codec_name", "?"), w, h,
                ", %.0f Mbit/s" % mbit if mbit else ""))
            if mbit > 60:
                reasons.append("%.0f Mbit/s - DLNA players usually top out near 60" % mbit)
            if h and w and abs(w / h - 16 / 9) > 0.35:
                reasons.append("unusual %dx%d aspect (TVs expect something near 16:9)"
                               % (w, h))
        elif st.get("codec_type") == "audio" and st.get("codec_name") in (
                "dts", "truehd", "mlp"):
            reasons.append("%s audio - Samsung does not decode it" % st["codec_name"])
        elif st.get("codec_type") == "data":
            reasons.append("extra data track (%s)" % st.get("codec_name", "?"))
    for reason in reasons:
        print("   ! %s" % reason)
    if reasons:
        print("   Try a lighter variant:  cast-gopro <n> -q proxy")


def check_codecs(path):
    """Warn about audio the TV cannot decode (DTS, TrueHD)."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "stream=codec_type,codec_name", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return
    bad = [l.split(",")[1] for l in out.strip().splitlines()
           if l.startswith("audio") and l.split(",")[1] in ("dts", "truehd", "mlp")]
    if bad:
        print("  ! %s audio - Samsung cannot decode it, playback will be silent."
              % "/".join(bad))
        print("    Fix with:  ffmpeg -i \"%s\" -c:v copy -c:a eac3 -b:a 640k \"%s\"\n"
              % (path, os.path.splitext(path)[0] + ".eac3.mkv"))


# ------------------------------------------------------------------ cast-tv
def find_tv(tv):
    """``(ip, avt_url)`` for the named or discovered TV, or ``(None, None)`` after printing why."""
    ip = tv
    if not ip:
        print("Looking for a TV...")
        devs = discover()
        if not devs:
            print("No DLNA renderer answered. Switch the TV on and try again,\n"
                  "or name it directly: cast-tv -t 192.168.1.50 film.mkv")
            return None, None
        ip, _, name = devs[0]
        print("Found: %s (%s)" % (name, ip))
    avt, _rc = control_urls(ip)
    if not avt:
        print("%s does not expose AVTransport (switched off?)." % ip)
        return ip, None
    return ip, avt


def cast(source, subs=None, tv=None, port=DEFAULT_PORT, title=None, debug=False,
         cookies=None):
    """Serve or relay ``source`` to the TV and follow playback until it ends. Returns an exit code."""
    ip, avt = find_tv(tv)
    if not avt:
        return 1
    relaying = source.startswith(("http://", "https://"))

    if relaying:
        # nothing is written to disk - we only pass the stream through
        name = os.path.basename(urllib.parse.urlparse(source).path) or "stream"
        opener = None
        if cookies:
            jar = http.cookiejar.MozillaCookieJar()
            try:
                jar.load(os.path.abspath(cookies), ignore_discard=True,
                         ignore_expires=True)
            except Exception as e:
                print("Could not read the cookie jar: %s" % e)
                return 1
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(jar))
            print("  cookies: %d from %s" % (len(jar), cookies))
        ext = os.path.splitext(name)[1].lower()
        upstream = Upstream(source, opener=opener)
        item = MediaItem(kind=kind_of_extension(ext) or "video",
                         title=title or os.path.splitext(name)[0],
                         mime=MIME.get(ext) or "video/mp4", source="link",
                         source_id=source, resolve=lambda: upstream, debug=debug)
        path = name
    else:
        path = os.path.abspath(source)
        if not os.path.isfile(path):
            print("No such file: %s" % path)
            return 1
        ext = os.path.splitext(path)[1].lower()
        kind = kind_of_extension(ext) or "video"
        if kind == "photo" and not is_allowed_photo(MIME.get(ext)):
            print("%s is a %s image; the TV is not sent GIF or raw stills."
                  % (os.path.basename(path), ext.lstrip(".").upper()))
            return 1
        if kind == "video":
            check_codecs(path)
        item = MediaItem(kind=kind,
                         title=title or os.path.splitext(os.path.basename(path))[0],
                         mime=MIME.get(ext, "application/octet-stream"), source="local",
                         source_id=path, path=path, size=os.path.getsize(path),
                         debug=debug)

    try:
        srv = Server(("0.0.0.0", port))
    except OSError as e:
        print("Cannot bind port %d: %s" % (port, e))
        return 1
    try:
        return _cast_on(srv, ip, avt, item, subs, relaying, source, debug)
    finally:
        # the CLI owns this server: retire what it registered and free the
        # port, whatever the exit path (SOAP failure, Ctrl+C, end of playback)
        for registered in srv.registry.items():
            srv.registry.retire(registered.id)
        srv.shutdown()
        srv.server_close()
        config.remove_photo_tmp_dir()


def _cast_on(srv, ip, avt, item, subs, relaying, source, debug):
    port = srv.port
    host = local_ip(ip)
    srv.set_host(host)
    base = "http://%s:%d" % (host, port)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.25},
                     daemon=True).start()

    registry = srv.registry
    if item.kind == "photo":
        # order matters: prepare, then publish the route, then tell the TV;
        # a conversion failure ends here, before any SOAP is sent
        from castlib import photos      # Pillow is needed for photos only
        photos.attach(registry)
        try:
            prep = photos.prepare(item)
        except CastError as e:
            print(e.message)
            return 1
        if debug:
            print("   photo: %s %dx%d, %d bytes, %s" % (
                prep.mime, prep.width, prep.height, prep.size, prep.profile))
    if subs:
        sub_path = os.path.abspath(subs)
        sub_ext = os.path.splitext(sub_path)[1].lower()
        sub = registry.add(MediaItem(kind="subtitle", title=os.path.basename(sub_path),
                                     mime=MIME.get(sub_ext, "text/plain"), source="local",
                                     source_id=sub_path, path=sub_path, debug=debug))
        item.caption = (sub_path, srv.media_url(sub))
    registry.add(item)
    if subs:
        sub.parent = item.id
    url = srv.media_url(item)

    try:
        soap(avt, AVT, "SetAVTransportURI",
             "<CurrentURI>%s</CurrentURI><CurrentURIMetaData>%s</CurrentURIMetaData>"
             % (escape(url), didl(item, url)))
        soap(avt, AVT, "Play", "<Speed>1</Speed>")
    except Exception as e:
        print("The TV rejected the request: %s" % e)
        return 1

    print("\n>  %s" % item.title)
    print("   %s %s  ->  %s" % ("relaying through" if relaying else "serving from",
                                base, ip))
    print("   Ctrl+C ends it (playback stops on the TV too)\n")

    started, waited = False, 0
    try:
        while True:
            time.sleep(2)
            try:
                info = soap(avt, AVT, "GetPositionInfo")
                state = tag(soap(avt, AVT, "GetTransportInfo"), "CurrentTransportState")
            except Exception:
                continue
            rel, dur = tag(info, "RelTime"), tag(info, "TrackDuration")
            sys.stdout.write("\r   %-12s %s / %s   " % (state, rel or "-", dur or "-"))
            sys.stdout.flush()
            if state in ("PLAYING", "PAUSED_PLAYBACK"):
                started = True
            elif not started:
                # TRANSITIONING is still an attempt; STOPPED after it is a refusal
                waited += 2
                if waited >= (40 if state == "TRANSITIONING" else 24):
                    print("\n   The TV never started playing.")
                    if item.kind == "video":
                        explain_failure(source if relaying else item.source_id)
                    break
                continue
            if state == "STOPPED" and started:
                print("\n   Finished.")
                break
    except KeyboardInterrupt:
        print()
        try:
            soap(avt, AVT, "Stop")
        except Exception:
            pass
        print("   Stopped.")
    return 0


def main_tv(argv=None):
    ap = argparse.ArgumentParser(prog="cast-tv", description="Play a video file on a Samsung TV.")
    ap.add_argument("source", nargs="?",
                    help="video file, or an http(s):// address to relay")
    ap.add_argument("-s", "--subs", help="external subtitle file (.srt)")
    ap.add_argument("-t", "--tv", default=os.environ.get("CAST_TV"),
                    help="TV address (default: discover it)")
    ap.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="HTTP port to serve on")
    ap.add_argument("--title", help="name to show instead of the file name")
    ap.add_argument("-d", "--debug", action="store_true",
                    help="log every request the TV makes")
    ap.add_argument("--stop", action="store_true", help="stop playback and exit")
    ap.add_argument("--list", dest="list_devices", action="store_true",
                    help="list discovered renderers")
    ap.add_argument("-c", "--cookies", metavar="FILE",
                    help="Netscape cookie jar, for material behind a login")
    args = ap.parse_args(argv)

    if args.list_devices:
        for ip, url, name in discover():
            print("%-16s %s" % (ip, name))
        return 0

    if args.stop:
        ip, avt = find_tv(args.tv)
        if not avt:
            return 1
        soap(avt, AVT, "Stop")
        print("Stopped.")
        return 0

    if not args.source:
        # discovery ran before this error in the one-shot script; keep the
        # message, and let Phase 3 turn the bare command into the UI
        ip, avt = find_tv(args.tv)
        if not avt:
            return 1
        ap.error("give a file or an address to play (or --stop / --list)")

    return cast(args.source, subs=args.subs, tv=args.tv, port=args.port,
                title=args.title, debug=args.debug, cookies=args.cookies)


# ---------------------------------------------------------------- cast-gopro
def show_gopro(items):
    if not items:
        print("The library is empty, or the filter matched nothing.")
        return
    width = max(len(i["name"]) for i in items)
    for n, i in enumerate(items, 1):
        print("%3d. %-*s  %s  %-6s %8s  %s" % (
            n, width, i["name"], i["date"] or "----------",
            i["res"] or "", net.human(i["size"]), i["kind"]))
    print("\nCast one:  cast-gopro <number>")


def main_gopro(argv=None):
    ap = argparse.ArgumentParser(prog="cast-gopro",
                                 description="Play GoPro cloud material on a TV.")
    ap.add_argument("what", nargs="?",
                    help="number from the listing, media id, or a gopro.com/v/... link")
    ap.add_argument("--token", help="store an access token from the browser and exit")
    ap.add_argument("-n", "--count", type=int, default=25, help="how many entries to list")
    ap.add_argument("-q", "--quality", choices=("auto", "source", "proxy"), default="auto",
                    help="auto takes the best variant, proxy a lighter preview")
    ap.add_argument("-t", "--tv", default=os.environ.get("CAST_TV"),
                    help="TV address (default: $CAST_TV, else discover it)")
    ap.add_argument("-p", "--port", type=int, help="HTTP port for cast-tv to serve on")
    ap.add_argument("--url-only", action="store_true",
                    help="print the address instead of casting it")
    args = ap.parse_args(argv)

    try:
        if args.token:
            path = gopro.save_token(args.token)
            print("Token stored in %s (yours only, mode 0600)." % path)
            return 0

        if args.what and args.what.startswith(("http://", "https://")):
            url, title = gopro.share_url(args.what), None
        elif args.what:
            tok = gopro.token()
            item = gopro.pick(args.what)
            print("Resolving: %s" % item["name"])
            url, title = gopro.library_url(item["id"], tok, args.quality), item["name"]
        else:
            show_gopro(gopro.list_media(gopro.token(), args.count))
            return 0
    except CastError as e:
        return _fail(e)

    if args.url_only:
        print(url)
        return 0
    return cast(url, tv=args.tv, port=args.port or DEFAULT_PORT, title=title)


# --------------------------------------------------------------- cast-photos
def main_photos(argv=None):
    ap = argparse.ArgumentParser(prog="cast-photos",
                                 description="Play a Google Photos video on a TV.")
    ap.add_argument("link", help="link to a video in Google Photos")
    ap.add_argument("-c", "--cookies", help="Netscape cookie jar (for private links)")
    ap.add_argument("-t", "--tv", default=os.environ.get("CAST_TV"),
                    help="TV address (default: $CAST_TV, else discover it)")
    ap.add_argument("-p", "--port", type=int, help="HTTP port for cast-tv to serve on")
    ap.add_argument("--url-only", action="store_true",
                    help="print the address instead of casting it")
    args = ap.parse_args(argv)

    try:
        op = net.opener_for(args.cookies)
        url = sharelink.resolve(args.link, op)
    except CastError as e:
        return _fail(e)
    if args.url_only:
        print(url)
        return 0
    # cookies travel on to the relay: signed Google addresses can be session-bound
    return cast(url, tv=args.tv, cookies=args.cookies, port=args.port or DEFAULT_PORT,
                title="Google Photos")


def _fail(err: CastError) -> int:
    print(err.message, file=sys.stderr)
    if err.hint:
        print(err.hint, file=sys.stderr)
    return 1
