---
change_id: cloud-source-ui
title: Pick media from GoPro, Google Photos and OneDrive in a UI, and cast it
status: new
created: 2026-09-07
updated: 2026-09-18
archived_at: null
---

## Notes

A UI for this tool: browse media from GoPro, Google Photos and OneDrive - separate
tabs are fine - and cast a selection to the Samsung TV.

Originally stated as: "UI do tej apki, ładowane pliki z GoPro, Google Photos
i OneDrive (mogą być osobne taby) i później ich castowanie na TV Samsunga."

The three sources are not alike, and that asymmetry is the whole shape of this change:

- **GoPro** is the only one that browses. `api.gopro.com/media/search` returns the
  library, so a tab can list it. It needs a bearer token lifted from a logged-in
  browser, and that token expires after a few hours - the UI has to make that
  visible rather than failing with a bare 401.
- **Google Photos** cannot be browsed at all. The Library API has only exposed
  user-picked items since 31 March 2025, so the entry point is a link to one video.
  A tab here is a paste field plus a history of what has been pasted, not a grid.
- **OneDrive** needs no API: the account is already mirrored to disk at
  `~/.onedrive-sync` (download_only, scope `/Pictures/OM Workspace/*`), which holds
  9 video files today. That tab is a local directory browse.

Casting itself is solved and verified against the TV; this change is only about
choosing what to cast. Worth carrying over: the TV refuses camera originals
(HEVC 3840x3360 at 119 Mbit/s), so a UI that offers a quality choice - as
`cast-gopro -q proxy` already does - avoids a dead end the CLI had to learn.

Undecided, and deliberately left to planning: whether this is a local web UI served
by the same process that already runs an HTTP server for the TV, or a desktop app.

## Decision

A local web page, served by `cast-ui` on port 8896 - not a desktop app. The process
already speaks HTTP for the TV's benefit, the page needs no toolchain and no
dependency beyond the standard library the rest of the tool holds to, and a browser
renders a media list better than Tk would.

The page does not reimplement any of the resolving or relaying. It builds the command
line a person would have typed - `cast-gopro 3 -q proxy`, `cast-photos <link> -c
cookies.txt`, `cast-tv <path>` - runs it as a child, and shows its output. So the path
verified against the TV stays the path that runs, and the page is only the argument
list.

## What was built

- `cast-ui`, with the three tabs the notes called for, and a per-row quality choice on
  GoPro so the dead end the CLI had to learn is not reachable from the page.
- Token expiry read from the JWT payload and shown as time remaining, which is the
  answer to "make that visible rather than failing with a bare 401".
- Google Photos history in `~/.config/cast-tv/photos-history.json`, since with nothing
  to browse the links already pasted are the closest thing to a library.
- OneDrive browse rooted at `~/.onedrive-sync`, configurable, and refusing to cast
  anything outside that root - a page open in a browser should not be able to name an
  arbitrary file.
- One cast at a time, and Stop sends the same SIGINT as Ctrl+C so the TV stops with it.

Verified: the page and every endpoint answer; a failing helper reports a sentence
instead of dropping the connection; the child-process plumbing was tested against a
stand-in that redraws its status line with `\r`, as `cast-tv` does; both the
choice-to-command layer and the token reader were tested including their refusals.

Not verified: a cast started from the page onto the real TV. That needs the Linux
laptop and the TV on the same network.

## Left out

- **Thumbnails.** `/media/search` returns no thumbnail address with the fields asked
  for, and guessing an undocumented endpoint - one call per row - was not worth it
  against a listing that already shows name, date, resolution and size.
- **Duration.** The API is already asked for it and the answer is discarded before the
  cache is written; carrying it through is a one-line change to `cast-gopro`, worth
  making next time that file is touched with a live token to test against.

## Windows 11 as well as Linux

The tool said "from Linux" and meant it. Making the same four commands work on Win11
took three real fixes, each verified against the same TV from a Windows laptop.

- **Nothing could start anything.** Windows will not execute an extensionless script,
  so every hand-off - `cast-gopro` to `cast-tv`, and the page to any of them - died with
  WinError 193. `castcloud.sibling()` now returns an argv list and names the
  interpreter on Windows; on Linux it returns exactly the one-element command it always
  ran, so nothing there changed.
- **Discovery found nothing at all.** One unbound multicast search leaves by whichever
  route the table prefers, and this laptop has seven addresses including a Hyper-V
  switch: the search went where no TV could hear it, and `--list` printed an empty
  list. The search now goes out of every address the machine holds, each with
  `IP_MULTICAST_IF` set, read together with `select`. Measured: unbound got 0 answers,
  bound to the Wi-Fi address got the TV immediately.
- **A refusal looked like a bug in the request.** The TV answered
  `SetAVTransportURI` with a bare HTTP 500 once. The reason was inside the SOAP fault:
  `errorCode 716, Resource not found`, which is the TV saying it could not fetch the
  address it was given - a blocked port at our end, not a malformed call. That code is
  now read and named, and where nothing arrived at all the firewall rule to add is
  printed. Same diagnosis serves Fedora, where firewalld would do the same thing.

Two things found while testing there, both fixed and both improvements on Linux too:

- A TV that seeks drops the connection mid-request, and `socketserver` answers that with
  a full traceback. Windows delivers it as a reset rather than a clean close, so a few
  seeks buried the log in stack traces. `Server.handle_error` now stays quiet for a
  dropped connection and nothing else.
- Stopping a GoPro or Photos cast from the page only signalled the resolver, leaving the
  `cast-tv` it had started behind - still serving, TV still playing. The child now runs
  in its own process group and Stop signals the group: `SIGINT` to the group on Linux,
  where cast-tv then stops the TV itself, and `CTRL_BREAK` on Windows, which clears the
  group but kills outright (0xC000013A, measured - Python does not turn it into
  KeyboardInterrupt), so there the TV is told separately.

Verified on Win11 against 192.168.50.142: discovery in 4.5s; a local file served with the
TV making ten requests including the tail-of-file range it uses to find the MP4 index; a
relayed remote clip playing 0:00 to 0:10 and reporting Finished; the page starting a cast,
showing the command's own output, and stopping it; and a two-deep cast leaving nothing
behind. Not shown: a decodable local file playing, since this machine has no ffmpeg to
make one - but the byte path off disk and decoding through the relay were each proven
separately.
