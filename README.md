# cast-tv

Push a local video file — or a remote stream — to a Samsung TV from Linux, with no app
installed on either end. A single Python file, standard library only.

```bash
cast-tv film.mkv                       # find the TV, serve the file, start playback
cast-tv film.mkv -s subtitles.srt      # with external subtitles
cast-tv "https://example.com/clip.mp4" # relay a remote stream; nothing touches the disk
cast-tv --list                         # show discovered renderers
cast-tv --stop                         # stop playback
```

Tizen exposes a UPnP/DLNA renderer, so the TV can be told to play a URL. `cast-tv` discovers
it over SSDP, serves the file over HTTP with `Range` support, and sends
`SetAVTransportURI` + `Play`. Nothing is transcoded and nothing is copied: the TV pulls the
bytes straight off the laptop's disk, and the remote pilot drives seeking as usual.

## Install

```bash
git clone <this repo> ~/Source/cast-tv
ln -s ~/Source/cast-tv/cast-tv ~/.local/bin/cast-tv
```

Needs Python 3 and nothing else. `ffprobe` is used, when present, only to warn about audio
codecs the TV cannot decode.

## Options

| Flag | Meaning |
| --- | --- |
| `-s, --subs FILE` | external `.srt`, passed via Samsung's `sec:CaptionInfoEx` extension |
| `-t, --tv IP` | skip discovery (also read from `$CAST_TV`) |
| `-p, --port N` | HTTP port to serve on, default 8895 |
| `-c, --cookies FILE` | Netscape cookie jar, for relaying material behind a login |
| `--list` | list discovered DLNA renderers |
| `--stop` | stop playback and exit |

## Relaying a remote stream

Given an `http(s)://` argument the laptop becomes a relay: it fetches upstream (over TLS, with
cookies if given) and re-serves the stream to the TV as plain HTTP, forwarding `Range` headers
both ways so seeking still works. Data passes through memory in 256 KB chunks and is never
written to disk.

This exists because the TV will not fetch an HTTPS URL itself — it accepts the SOAP call
without complaint and then sits in `STOPPED` — and because it has no way to authenticate
against a cloud account.

## Cloud sources

Two companion commands resolve a cloud item to a direct stream and hand it to the relay, so
nothing is downloaded in that case either.

```bash
cast-gopro --token eyJhbGc...              # store a browser token once
cast-gopro                                 # list the GoPro cloud library
cast-gopro 3                               # cast the third entry
cast-gopro https://gopro.com/v/AbCdE       # public GoPro share link
cast-photos https://photos.app.goo.gl/xxx  # Google Photos share link
cast-photos <private link> -c cookies.txt  # private item, with your cookies
```

**GoPro** talks to `api.gopro.com` with a bearer token copied out of a logged-in browser
(devtools, the `Authorization` header); it expires after a few hours. The library listing is
cached so items can be picked by number, and the highest available variation that verifies as
video is the one cast.

**Google Photos** has no usable API for this — since 31 March 2025 the Library API only exposes
items the user explicitly picks — so the starting point is a link to one video. The page is
parsed for candidate stream URLs, each candidate is probed with a one-byte range request, and
the first that answers as video wins. Public share links need nothing; private links need a
cookie jar.

Both resolvers are written defensively because neither format is documented and both can change
without notice: when nothing resolves, the command says what it saw instead of failing blind.

## Limitations

**Audio codecs.** Video is passed through untouched, so the TV has to decode it. H.264, HEVC,
AV1 and VP9 with AAC/AC3/EAC3 are fine; **DTS and TrueHD are not decoded** — picture plays,
sound is silent. `cast-tv` probes for this before sending and prints the `ffmpeg` command that
re-encodes just the audio.

**The laptop must stay awake** for the whole session; the file is streamed, not handed over.

**Subtitles** as a separate `.srt` rely on a Samsung-specific DLNA extension. Subtitles muxed
into an MKV work on their own.

## Repository tooling

`ai-toolkit sync` installs the managed authoring skills locally. They are deliberately not
tracked here — see `.gitignore` — and the recovery channel is never installed into this repo,
because it carries course-licensed material that must not enter a public repository.

## Tested on

Samsung QE83S85FAEXXH (83" OLED, Tizen, 2025) and Fedora 44. Any DLNA renderer exposing
`AVTransport:1` should work; the subtitle path is Samsung-specific.
