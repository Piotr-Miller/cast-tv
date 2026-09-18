# cast-tv

Put a video or a photo on a Samsung TV - from a local disk, a GoPro cloud library, OneDrive or
Google Photos - from Linux or Windows, with no app installed on the TV. A local web UI browses
the three clouds, and the same process serves the media, so the phone on the couch can pick what
plays on the big screen.

```bash
cast-tv                                # open the UI (and print the address for the phone)
cast-tv film.mkv                       # find the TV, serve the file, start playback
cast-tv film.mkv -s subtitles.srt      # with external subtitles
cast-tv IMG_4823.HEIC                  # a photo; HEIC is converted to JPEG on the fly
cast-tv a.jpg b.heic c.mp4 -i 5        # a slideshow: photos hold 5 s, videos play to the end
cast-tv "https://example.com/clip.mp4" # relay a remote stream
cast-tv --list                         # show discovered renderers
cast-tv --stop                         # stop playback
```

Tizen exposes a UPnP/DLNA renderer, so the TV can be told to play a URL. `cast-tv` discovers
it over SSDP, serves the material over HTTP with `Range` support, and sends
`SetAVTransportURI` + `Play`. Video is not transcoded: the TV pulls the bytes straight off the
laptop's disk (or through the laptop from the cloud), and the remote drives seeking as usual.

## Install

Python 3.10 or newer, then [pipx](https://pipx.pypa.io/), which puts `cast-tv`, `cast-gopro`
and `cast-photos` on the path on both systems:

```bash
# Fedora
sudo dnf install pipx
pipx install git+https://github.com/Piotr-Miller/cast-tv

# Windows (PowerShell)
py -m pip install --user pipx
py -m pipx ensurepath          # then open a new terminal
pipx install git+https://github.com/Piotr-Miller/cast-tv
```

Dependencies come with it: `pillow` and `pillow-heif` (photo conversion), `ifaddr` (discovery on
every network interface), `platformdirs` (config paths). `ffprobe` is optional and only used to
warn about audio codecs the TV cannot decode; on Windows it is a manual download.

From a checkout, for development:

```bash
python -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/python -m castlib          # the UI
.venv/bin/python -m pytest
```

The extensionless scripts at the root (`cast-tv`, `cast-gopro`, `cast-photos`) still work when
symlinked into `~/.local/bin`, the way this was installed before pipx.

## The UI

`cast-tv` with no arguments starts the server on port 8895, prints its addresses - `localhost`,
then every LAN address of the machine - and opens the browser. Open the LAN address on a phone
on the same network and it is the same UI.

- **The TV** is shown in the header: the first renderer discovery finds, or the one chosen
  before (remembered), or `-t` / `$CAST_TV`. Several renderers give a dropdown; none gives a
  banner that lists every network interface the search went out on and how many devices
  answered on each, with "search again" and a field for the TV's address.
- **Three tabs**, each behind its own connection step - GoPro, OneDrive, Google Photos (setup
  below). Ticking items builds a selection that survives switching tabs, so one slideshow can
  mix sources.
- **Casting** replaces whatever plays. **Start show** plays the selection in the order it was
  ticked: a photo holds for the interval (8 s by default, adjustable, remembered), a video plays
  to its end. Pause, next, previous and stop are in the slideshow bar.
- **Diagnostics** keep the last 50 errors, each on the item or source it belongs to: an expired
  token, a TV that never fetched a byte (with the firewall command), DTS audio (with the
  `ffmpeg` line that fixes it), a source too heavy for the TV.

The process stays in the foreground: it is what streams to the TV. `Ctrl+C` stops playback on
the TV and ends it; on Windows, closing the console window does the same. Starting a second
`cast-tv` while one runs opens the running one's UI instead.

**Exposure.** The server listens on the LAN, because the TV has to reach it. `/api` and `/ui`
answer only requests whose `Host` is this machine and whose `Origin`, if any, matches it, so a web
page open in the browser cannot drive the TV; media addresses carry a per-process token and are
exact-match lookups.

## Firewall

The TV connects *inbound* to port 8895. When the port is closed the TV fetches nothing, and
cast-tv says so ("the TV fetched zero bytes") with the command for this system:

```bash
sudo firewall-cmd --add-port=8895/tcp                     # Fedora, until reboot
sudo firewall-cmd --permanent --add-port=8895/tcp && sudo firewall-cmd --reload
```

```powershell
# Windows, as administrator; or accept the prompt on the first start
netsh advfirewall firewall add rule name="cast-tv" dir=in action=allow protocol=TCP localport=8895
```

Windows also blocks silently when the network is classed **Public**; make the home network
Private. The startup banner prints the same hint.

A laptop managed by an employer can carry a firewall policy that blocks every incoming
connection. No allow rule outranks it, so the command above cannot help, and casting from that
machine is not possible. On Windows cast-tv checks for such a rule at startup (no administrator
rights needed) and, when it finds one, says so in the banner and in the "fetched nothing" error
instead of offering the command.

## Sources

### GoPro

GoPro has no public login for third-party apps, so the tab takes a bearer token copied out of a
logged-in browser: open the GoPro cloud library, open the devtools network tab, and copy the
`Authorization` header of any `api.gopro.com` request. Paste it into the tab (or
`cast-gopro --token eyJhbGc...`). It expires after a few hours; the tab then shows a banner over
the list and takes a new paste in place. `$GOPRO_TOKEN` overrides the stored token.

Camera originals can be too much for a TV to decode - a 5.3K clip runs at 119 Mbit/s in a
3840x3360 frame, which this TV refuses outright - so a heavy clip defaults to the proxy variant
the cloud already holds, and the source stays one click away.

### OneDrive

Sign-in is Microsoft's device code flow: the tab shows a code and the Microsoft address to enter
it at, and the code can be entered on any device - the phone included. The refresh token is kept and
renewed silently. The whole drive is browsable from the root; only photos and videos are listed.

The app ships with the owner's Entra app registration. To use your own: register an app in
the Entra admin centre with *Personal Microsoft accounts* among the supported account types,
add the *Mobile and desktop applications* platform, set **Allow public client flows = Yes**
(Authentication, Advanced settings), and put its Application (client) ID in
`$ONEDRIVE_CLIENT_ID`.

### Google Photos

Since 31 March 2025 the Library API only exposes items the user explicitly picks, so the tab
uses Google's **Picker API**: connect once, then "Pick in Google Photos" opens Google's own
picker - its link works on the phone too - and whatever is picked lands in the grid. Picks last
for the session; the connection survives a restart.

One-time setup: a Google Cloud project with the **Photos Picker API** enabled, an OAuth consent
screen (Testing mode, with yourself as a test user, is enough), and an OAuth client of type
**Desktop app**. Download its JSON and copy it to `google-client.json` in the config directory
(below), or point `$GOOGLE_CLIENT_JSON` at it. The consent itself must be given in a browser on
the machine running cast-tv: Google sends it back to `127.0.0.1`.

A picked **video** is cast as its original by default, and the original is **downloaded before
casting**: its host ignores range requests, and the TV gives up waiting for the end of the file.
It goes to a per-process directory under `/var/tmp` (`%TEMP%` on Windows), deleted when the item
leaves the session or cast-tv exits; a directory left by a killed run is removed at the next
start. One download may be at most `$CAST_TV_DOWNLOAD_MAX_GB` GiB (default 16, or a quarter of
the filesystem if that is less), all downloads together at most a quarter of it, and a download
stops before a write would leave less than 5 % of it free (at least 1 GiB). The tile's **1080p
stream** variant is relayed and downloads nothing.

**Share links** from other people's libraries still work, pasted into the tab or given to
`cast-photos`: the page is parsed for candidate stream URLs, each is probed with a one-byte range
request, and the first that answers as video wins. Share links cast videos only. Public links
need nothing; private ones need a cookie jar (`-c cookies.txt`).

## Command line

| `cast-tv` flag | Meaning |
| --- | --- |
| `-s, --subs FILE` | external `.srt`, passed via Samsung's `sec:CaptionInfoEx` extension |
| `-t, --tv IP` | skip discovery (also read from `$CAST_TV`) |
| `-p, --port N` | HTTP port to serve on, default 8895 |
| `-i, --interval S` | seconds a photo holds in a slideshow (default: the saved setting, 8) |
| `--show` | run a slideshow even for a single file |
| `--title TEXT` | name to show instead of the file name |
| `-c, --cookies FILE` | Netscape cookie jar, for relaying material behind a login |
| `-d, --debug` | log every request the TV makes |
| `--no-browser` | start the UI without opening a browser |
| `--list` | list discovered DLNA renderers |
| `--stop` | stop playback and exit |

```bash
cast-gopro                                 # list the GoPro cloud library
cast-gopro 3                               # cast the third entry
cast-gopro 3 -q proxy                      # ... as the lighter proxy variant
cast-gopro https://gopro.com/v/AbCdE       # public GoPro share link
cast-photos --pick                         # pick in Google Photos' own picker, then cast
cast-photos https://photos.app.goo.gl/xxx  # Google Photos share link
cast-photos <private link> -c cookies.txt  # private item, with your cookies
```

`--url-only` on either prints the resolved address instead of casting it.

## Relaying a remote stream

Given an `http(s)://` address, or a cloud item, the laptop becomes a relay: it fetches upstream
(over TLS, with the source's credentials) and re-serves the stream to the TV as plain HTTP,
forwarding `Range` both ways so seeking still works. Data passes through memory in 256 KB chunks
and is never written to disk. Cloud download addresses expire after about an hour, so they are
resolved when the TV opens the stream, and resolved again if the cloud refuses a stale one.

A source that ignores `Range` and answers `200` with the whole file is compensated for: the
relay skips to the requested offset itself and synthesises the `206` the TV expects. Without
that the TV asks for the offset of the MP4 index, receives the start of the file, and quietly
refuses to play. `--debug` prints every request the TV makes, which is how that was found.

This exists because the TV will not fetch an HTTPS URL itself - it accepts the SOAP call
without complaint and then sits in `STOPPED` - and because it has no way to authenticate
against a cloud account.

## Photos

A photo is prepared before the TV hears about it: fetched whole, turned upright by its EXIF
orientation, converted to JPEG when it is HEIC, WebP, oriented, or a JPEG carrying extra images
(a Pixel Ultra HDR or motion photo), downscaled to fit 4096x4096, and kept in a bounded
per-process cache (256 MB) that disappears with the process. JPEG and PNG that need none of that
are served as they are. GIF, raw and other stills the TV cannot show are not listed.

## Where files live

| | Linux | Windows |
| --- | --- | --- |
| tokens, settings, `google-client.json` | `~/.config/cast-tv` | `%APPDATA%\cast-tv` |
| listing cache (metadata only) | `~/.cache/cast-tv` | `%LOCALAPPDATA%\cast-tv\Cache` |
| converted photos, per process | `/tmp/cast-tv-photos-*` | `%TEMP%\cast-tv-photos-*` |
| downloaded Google videos, per process | `/var/tmp/cast-tv-videos-*` | `%TEMP%\cast-tv-videos-*` |

Token files are written readable by their owner only (mode 0600 on Linux).

## Limitations

**Audio codecs.** Video is passed through untouched, so the TV has to decode it. H.264, HEVC,
AV1 and VP9 with AAC/AC3/EAC3 are fine; **DTS and TrueHD are not decoded** - picture plays,
sound is silent. `cast-tv` probes local files for this before sending and prints the `ffmpeg`
command that re-encodes just the audio.

**The machine must stay awake** for the whole session; the material is streamed, not handed
over. While something plays, cast-tv holds a `systemd-inhibit` idle and sleep lock on Linux, and
`SetThreadExecutionState` on Windows (which keeps the display on as well); both go when playback
stops or cast-tv exits.

**Subtitles** as a separate `.srt` rely on a Samsung-specific DLNA extension. Subtitles muxed
into an MKV work on their own.

**Photos** are decoded on the laptop; a 20-megapixel HEIC from OneDrive took about 6 s from
the click to the TV fetching it. A slideshow prepares the next two photos ahead.

**Google Photos** picks are not kept across restarts, and the one-time consent must happen on
the host. **GoPro** tokens last hours, not days.

**Local folders** are not browsable from the UI (anything on the LAN could list them); local files
are cast from the command line, and then show up in the UI for that session.

## Repository tooling

`ai-toolkit sync` installs the managed authoring skills locally. They are deliberately not
tracked here - see `.gitignore` - and the recovery channel is never installed into this repo,
because it carries course-licensed material that must not enter a public repository.

Tests run on every pull request on `ubuntu-latest` and `windows-latest`
(`.github/workflows/test.yml`); there is no TV in CI, so the cast lifecycle is covered with a
scripted fake of the SOAP calls and checked by hand against the real TV.

## Tested on

Samsung QE83S85FAEXXH (83" OLED, Tizen, 2025) and Fedora 44, against a live GoPro cloud library,
a personal OneDrive and a live Google Photos account. Any DLNA renderer exposing `AVTransport:1`
should work; the subtitle path is Samsung-specific.
