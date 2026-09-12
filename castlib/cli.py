"""The three commands, on top of ``App`` and the cast supervisor.

``cast-tv`` with no arguments starts the long-lived server and opens the UI;
``cast-tv film.mkv`` casts one file and follows it as the one-shot script
did; ``cast-tv a.jpg b.heic c.mp4`` runs a slideshow through the same
engine the UI uses. ``cast-gopro`` and ``cast-photos`` resolve in process and
call ``cast()`` directly instead of spawning a second server.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import os
import sys
import urllib.parse
import urllib.request
import webbrowser

from castlib import net
from castlib.app import AlreadyRunning, App
from castlib.diagnostics import check_codecs
from castlib.discovery import control_urls, discover
from castlib.dlna import AVT, soap
from castlib.errors import CastError
from castlib.items import MediaItem, Upstream
from castlib.media import MIME, kind_of_extension
from castlib.server import Server
from castlib.sources import gopro, sharelink
from castlib.sources.local import item_for_path

DEFAULT_PORT = 8895


# ------------------------------------------------------------------ cast-tv
def find_tv(tv):
    """``(ip, avt_url, name)`` for the named or discovered TV, or ``(None, None, None)`` after printing why."""
    ip, name = tv, tv
    if not ip:
        print("Looking for a TV...")
        devs = discover()
        if not devs:
            print("No DLNA renderer answered. Switch the TV on and try again,\n"
                  "or name it directly: cast-tv -t 192.168.1.50 film.mkv")
            return None, None, None
        ip, _, name = devs[0]
        print("Found: %s (%s)" % (name, ip))
    avt, _rc = control_urls(ip)
    if not avt:
        print("%s does not expose AVTransport (switched off?)." % ip)
        return ip, None, name
    return ip, avt, name


def _bind(port):
    try:
        return Server(("0.0.0.0", port))
    except OSError as e:
        print("Cannot bind port %d: %s" % (port, e))
        return None


def _relay_item(source, title, debug, cookies):
    """A ``MediaItem`` that relays ``source``; prints and returns ``None`` when the cookie jar is unreadable."""
    # nothing is written to disk - we only pass the stream through
    name = os.path.basename(urllib.parse.urlparse(source).path) or "stream"
    opener = None
    if cookies:
        jar = http.cookiejar.MozillaCookieJar()
        try:
            jar.load(os.path.abspath(cookies), ignore_discard=True, ignore_expires=True)
        except Exception as e:
            print("Could not read the cookie jar: %s" % e)
            return None
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        print("  cookies: %d from %s" % (len(jar), cookies))
    ext = os.path.splitext(name)[1].lower()
    upstream = Upstream(source, opener=opener)
    return MediaItem(kind=kind_of_extension(ext) or "video",
                     title=title or os.path.splitext(name)[0],
                     mime=MIME.get(ext) or "video/mp4", source="link",
                     source_id=source, resolve=lambda: upstream, debug=debug)


def _print_codec_warning(path):
    bad, cmd = check_codecs(path)
    if bad:
        print("  ! %s audio - Samsung cannot decode it, playback will be silent." % "/".join(bad))
        print("    Fix with:  %s\n" % cmd)


def cast(source, subs=None, tv=None, port=DEFAULT_PORT, title=None, debug=False,
         cookies=None):
    """Serve or relay ``source`` to the TV and follow playback until it ends. Returns an exit code."""
    ip, avt, name = find_tv(tv)
    if not avt:
        return 1
    relaying = source.startswith(("http://", "https://"))
    if relaying:
        item = _relay_item(source, title, debug, cookies)
        if item is None:
            return 1
    else:
        try:
            item = item_for_path(source, title=title, debug=debug)
        except CastError as e:
            print(e.message)
            return 1
        if item.kind == "video":
            _print_codec_warning(item.path)
    subtitle = None
    if subs:
        sub_path = os.path.abspath(subs)
        sub_ext = os.path.splitext(sub_path)[1].lower()
        subtitle = MediaItem(kind="subtitle", title=os.path.basename(sub_path),
                             mime=MIME.get(sub_ext, "text/plain"), source="local",
                             source_id=sub_path, path=sub_path, debug=debug)
    return _cast_item(item, (ip, avt, name), port, debug, subtitle=subtitle)


def _cast_item(item, tv, port, debug, subtitle=None):
    """Serve ``item`` from a fresh server to the TV ``(ip, avt, name)`` and follow playback."""
    ip, avt, name = tv
    relaying = item.path is None
    srv = _bind(port)
    if srv is None:
        return 1
    app = App(srv, debug=debug)
    app.codec_check = False                  # printed above, once
    try:
        app.serve()
        app.use_tv(ip, avt, name)
        if not relaying:
            app.local.remember(item)         # the UI may re-cast it or put it in a show
        return _follow(app, app.cast(item, subtitle=subtitle), ip, relaying, debug)
    finally:
        # the CLI owns this server: retire what it registered and free the
        # port, whatever the exit path (SOAP failure, Ctrl+C, end of playback)
        app.close()


def _follow(app, c, ip, relaying, debug):
    """Print what the one-shot script printed while a cast runs; returns the exit code."""
    c.sent.wait()
    item = c.item
    if c.state == "failed":
        print(c.reason.message)
        if c.reason.hint:
            print("   %s" % c.reason.hint)
        return 1
    if debug and item.prepared is not None:
        prep = item.prepared
        print("   photo: %s %dx%d, %d bytes, %s" % (
            prep.mime, prep.width, prep.height, prep.size, prep.profile))
    base = "http://%s:%d" % (app.server.host, app.server.port)
    print("\n>  %s" % item.title)
    print("   %s %s  ->  %s" % ("relaying through" if relaying else "serving from", base, ip))
    print("   Ctrl+C ends it (playback stops on the TV too)\n")
    last = None
    try:
        while not c.done.wait(0.5):
            line = (c.tv_state, c.position, c.duration)
            if line != last and c.tv_state:
                sys.stdout.write("\r   %-12s %s / %s   " % (
                    c.tv_state, c.position or "-", c.duration or "-"))
                sys.stdout.flush()
                last = line
    except KeyboardInterrupt:
        print()
        app.stop()
        print("   Stopped.")
        return 0
    if c.state == "failed":
        print("\n   %s" % c.reason.message)
        if c.media_line:
            print("   media: %s" % c.media_line)
        for reason in c.reasons:
            print("   ! %s" % reason)
        if c.reasons:
            print("   Try a lighter variant:  cast-gopro <n> -q proxy")
        elif c.reason.hint:
            print("   %s" % c.reason.hint)
    elif c.state == "stopped":
        print("\n   Finished.")
    elif c.state == "replaced":
        return _taken_over(app)
    return 0


def _taken_over(app):
    """The UI took playback over: this process now hosts it, so stay until Ctrl+C."""
    print("\n   Taken over from the UI; serving on until Ctrl+C.")
    return app.run_forever()


def show(sources, interval=None, tv=None, port=DEFAULT_PORT, debug=False):
    """Run a slideshow over local files from the command line. Returns an exit code."""
    items = []
    for source in sources:
        if source.startswith(("http://", "https://")):
            print("A slideshow takes local files; %s is an address." % source)
            return 1
        try:
            item = item_for_path(source, debug=debug)
        except CastError as e:
            print(e.message)
            return 1
        if item.kind == "video":
            _print_codec_warning(item.path)
        items.append(item)
    ip, avt, name = find_tv(tv)
    if not avt:
        return 1
    srv = _bind(port)
    if srv is None:
        return 1
    app = App(srv, debug=debug)
    app.codec_check = False
    try:
        app.serve()
        app.use_tv(ip, avt, name)
        for item in items:
            app.local.remember(item)
        try:
            sh = app.show(items, interval)
        except CastError as e:
            return _fail(e)
        photos = sum(1 for i in items if i.kind == "photo")
        print("\n>  Slideshow: %d items (%d photos), a photo holds %g s" % (
            len(items), photos, sh.interval))
        print("   serving from http://%s:%d  ->  %s" % (app.server.host, app.server.port, ip))
        print("   UI: http://localhost:%d/ui/  ·  Ctrl+C ends it\n" % app.server.port)
        last = None
        try:
            while not sh.done.wait(0.5):
                c = sh.current
                if c is None:
                    continue
                line = (sh.index, c.state, c.tv_state, c.position)
                if line != last:
                    sys.stdout.write("\r   [%d/%d] %-28s %-10s %s   " % (
                        sh.index + 1, len(items), c.item.title[:28], c.state,
                        (c.position + " / " + c.duration) if c.item.kind == "video" and c.position else ""))
                    sys.stdout.flush()
                    last = line
        except KeyboardInterrupt:
            print()
            app.stop()
            print("   Stopped.")
            return 0
        if sh.state == "cancelled" and app.owner is not None:
            return _taken_over(app)
        print("\n   Show %s.%s" % (sh.state, " %d skipped." % sh.skipped if sh.skipped else ""))
        for err in app.errors.list():
            print("   ! %s" % err["message"])
        return 0
    finally:
        app.close()


def ui(port=DEFAULT_PORT, tv=None, debug=False, browser=True):
    """The long-lived server with the UI; returns when Ctrl+C ends it."""
    try:
        app = App.start(port, tv=tv, debug=debug, browser=browser)
    except AlreadyRunning as e:
        print("cast-tv is already running: %s" % e.url)
        if browser:
            try:
                webbrowser.open(e.url)
            except Exception:
                pass
        return 0
    except OSError as e:
        print("Cannot bind port %d: %s" % (port, e))
        return 1
    return app.run_forever()


def main_tv(argv=None):
    ap = argparse.ArgumentParser(
        prog="cast-tv",
        description="Play a video or photo on a Samsung TV; with no arguments, open the UI.")
    ap.add_argument("source", nargs="*",
                    help="video or photo file, or an http(s):// address to relay; "
                         "several files run a slideshow")
    ap.add_argument("-s", "--subs", help="external subtitle file (.srt)")
    ap.add_argument("-t", "--tv", default=os.environ.get("CAST_TV"),
                    help="TV address (default: discover it)")
    ap.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="HTTP port to serve on")
    ap.add_argument("-i", "--interval", type=float,
                    help="seconds a photo stays on screen in a slideshow (default: the saved setting, 8)")
    ap.add_argument("--show", action="store_true",
                    help="run a slideshow even for a single file")
    ap.add_argument("--title", help="name to show instead of the file name")
    ap.add_argument("-d", "--debug", action="store_true",
                    help="log every request the TV makes")
    ap.add_argument("--stop", action="store_true", help="stop playback and exit")
    ap.add_argument("--list", dest="list_devices", action="store_true",
                    help="list discovered renderers")
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open the UI in a browser")
    ap.add_argument("-c", "--cookies", metavar="FILE",
                    help="Netscape cookie jar, for material behind a login")
    args = ap.parse_args(argv)

    if args.list_devices:
        for ip, url, name in discover():
            print("%-16s %s" % (ip, name))
        return 0

    if args.stop:
        ip, avt, _ = find_tv(args.tv)
        if not avt:
            return 1
        soap(avt, AVT, "Stop")
        print("Stopped.")
        return 0

    sources = list(args.source)
    if sources == ["ui"] and not os.path.exists("ui"):
        sources = []                      # python -m castlib ui, from a checkout
    if not sources:
        return ui(port=args.port, tv=args.tv, debug=args.debug, browser=not args.no_browser)
    if len(sources) > 1 or args.show:
        if args.subs:
            ap.error("subtitles go with a single file, not a slideshow")
        return show(sources, interval=args.interval, tv=args.tv, port=args.port,
                    debug=args.debug)
    return cast(sources[0], subs=args.subs, tv=args.tv, port=args.port,
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
            url = gopro.share_url(args.what)
            if args.url_only:
                print(url)
                return 0
            return cast(url, tv=args.tv, port=args.port or DEFAULT_PORT)
        if not args.what:
            show_gopro(gopro.list_media(gopro.token(), args.count))
            return 0

        # a library entry: the same Source the UI uses, in process
        picked = gopro.pick(args.what)
        print("Resolving: %s" % picked["name"])
        source = gopro.GoProSource()
        item = source.resolve(picked["id"], args.quality)
        if picked.get("name") and picked["name"] != picked["id"]:
            item.title = picked["name"]
        if args.url_only:
            print(item.resolve().url)
            return 0
    except CastError as e:
        return _fail(e)

    ip, avt, name = find_tv(args.tv)
    if not avt:
        return 1
    return _cast_item(item, (ip, avt, name), args.port or DEFAULT_PORT, False)


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
