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
- The token's standing shown up front rather than discovered as a bare 401: when it was
  stored, and how GoPro answered the last time it was used. This started out reading an
  expiry from the token, which turned out to be impossible - see the GoPro section below.
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

Not verified at the time of writing: a cast started from the page onto the real TV, which
needed the TV on the same network. Both sections below close that, from Windows.

## Left out

- **Thumbnails.** `/media/search` returns no thumbnail address with the fields asked
  for, and guessing an undocumented endpoint - one call per row - was not worth it
  against a listing that already shows name, date, resolution and size.
- **Duration.** `cast-gopro` asks `/media/search` for it and the answer never contains
  it: against a live library the field comes back absent on every item, so the listing
  cannot show a length no matter what is done at this end. This was written down twice as
  a one-line change worth making, which a live token then disproved.

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
relayed remote clip playing 0:00 to 0:10 and reporting Finished; a local file off disk
doing the same, the TV asking for a range from the middle of it on the way; the page
starting a cast, showing the command's own output, and stopping it; and a two-deep cast
leaving nothing behind.

## The GoPro tab on Windows, without an account

Most of what this tab does happens before GoPro is ever asked, so most of it can be
checked with a token of one's own making. Against fake JWTs - a structure, no valid
signature - the page walks the whole scale: no token at all puts the entire how-to on
the page instead of failing quietly; an expiry in the past reads `token: expired`
without a single call to GoPro; two hours out reads `1h 58m left` in green; seven
minutes out reads `7m left` in amber. Storing one through the page's own bar works on
Windows, and the refresh that follows drew a real 401 from api.gopro.com, which the page
showed with the how-to rather than as a bare failure. The paste-twice repair and the
"no listing cached" hint were checked on the command line there too.

Then a real token arrived, and the first thing it showed is that the headline feature was
built on a false premise. **GoPro's token is not a JWT but a JWE**: five parts, a header
naming `alg` and `enc`, and a payload that is encrypted rather than merely encoded. Its
expiry cannot be read - not here, not anywhere without GoPro's key - so `token: 2h 14m
left` was a thing only a token of my own making would ever have produced. A fake stood in
for the real thing and agreed with the assumption that made it.

What the page says now is what can be known without spending a call: when the token was
stored, since they last a few hours, and how GoPro answered the last time it was used -
`token: working, stored 5m ago`, or `token: rejected` once a call comes back 401. The
expiry path is kept for a token that does carry a readable one, and the amber past three
hours is marked in the code as a hint rather than knowledge.

With that token the rest went through on Windows: a listing of 60 items, and item 1 cast
from the page as a proxy, which resolved to `high_res_proxy_mp4` at 9 MB in place of a
136 MB 3360p original and played 0:00 to 0:09 on the TV. Stopping a live two-deep cast
was checked too, which until now had only been tested against stand-ins: three Python
processes while it played, Stop from the page, one left, and the TV reporting STOPPED.

One flaw the real library exposed: every row defaulted to `auto`, and `auto` means "best
variation", which for a camera original is exactly the variant this TV refuses - and all
60 items are 3360p. A page whose purpose was to keep that dead end out of reach opened on
it. The rows now open on the proxy.

Found while doing this, and the reason it was worth doing: five hints named the commands
as `cast-gopro ...` and `cast-photos ...`. That is correct on Linux, where a shebang and
a symlink make them commands, and on Windows it sends the reader straight into the
WinError 193 this change had just finished fixing - and the page shows these strings
verbatim, so they are UI. `castcloud.how_to_run()` renders them per platform now, and
the Linux wording was checked byte-for-byte against what it said before. The config and
cache paths were being printed with mixed separators as well, since expanduser leaves
`C:\\Users\\pmill/.config/cast-tv`; both are normalised now, because both are shown to
people.

Not exercised from Windows: the Google Photos tab against a live share link, for want of
one on that machine. It reaches Google over plain HTTP and hands off through the launcher
every other path here proved, so what is untested is Google's own answer rather than
anything the platform does differently - and its failure path was seen, since a
deliberately bad link produced the cookie advice as intended.
