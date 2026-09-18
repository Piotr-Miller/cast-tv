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
- **Duration.** Written off here as impossible, then found: the field is
  `source_duration`, in milliseconds, and it has been in every answer all along.
  `cast-gopro` asked for `duration`, which does not exist, so the API returned nothing
  and the conclusion drawn from that was "the API cannot tell us" rather than "the wrong
  field was asked for". The listing now caches it; showing it is UI work still to do.

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

## What a live library showed, and where this stands

A real token turned up three things that no amount of testing against my own fakes
would have.

**Photos are in the library, and casting one asked the TV to play a picture as a
film.** 12 of the 60 items are Photos - phone pictures synced into the GoPro cloud - and
a Photo carries exactly one variation, a jpg. `library_url` filtered that out as "not
video", which left only the `files` entry; the CDN labels that `binary/octet-stream`,
`is_video()` accepts octet-stream because GoPro's source mp4s arrive that way, and so a
JPEG sailed through as video and was announced to the TV as `object.item.videoItem`.
The TV answered that the file is not supported, which was the only honest thing in the
whole chain. Stills are now recognised before the video ranking runs, `cast-tv` knows
the image mime types, announces `object.item.imageItem.photo`, sends `Interactive`
rather than `Streaming` transfer mode and a JPEG profile in contentFeatures. Verified:
the TV fetched the jpg and displayed it.

**Thumbnails are reachable after all.** `/media/{id}/thumbnail` answers 406 to every
Accept header tried, and the `sprites` array is empty - but `available_labels` lists a
`large` label that `/download` does not return by default, and
`/download?labels=large` hands over a jpg at 1280x1120. For a Photo there is no `large`
and the only still is the 4000x3000 source, so a photo's thumbnail costs 3.6 MB unless
something downsizes it. One signed URL per item, so a page wanting 60 of them needs 60
calls - which argues for resolving them lazily, per row, as the rows come into view.
Not built yet.

**The design in the canvas is a wider thing than what exists.** Five artboards - the
app with a gate and a list, a slideshow, a phone layout, three gates side by side, and a
states-and-diagnostics board. Its own annotations carry the reasoning: clicking a video
throws it at the TV while clicking a photo *selects it for a slideshow*, and the queue
may mix GoPro with OneDrive; the slideshow is driven by the laptop because DLNA has no
playlist, so the queue and the timer live at our end; the phone layout wants a device
code rather than a redirect to localhost, because it is the same server opened from the
LAN. So a photo was never meant to be cast on its own - it was meant to join a queue.
What exists today is the list, three tabs, and the states. The gate, the slideshow, the
phone layout and the tiled grid with thumbnails are all still design rather than code.

Also settled: the thumbnails I sketched in the option preview when asking which shape
this UI should take were never built, and saying so only in this file was not enough -
they were taken, reasonably, for something the tool already did on another machine.

## The grid, built from the canvas

The first thing the page had got wrong was that it was written without opening the design
that already existed. The canvas is readable in full through the artifact - every
artboard's markup, and a `DCLogic` class per artboard carrying its state, its sample data
and what each click does - so there was never a need to ask for an export. What the
page takes from `Main` now: the warm oklch palette at hue 65 with the amber accent, Archivo
and IBM Plex Mono, the header with the TV named in a chip, tabs with a hint line under
each label, the All / Videos / Photos filters, and the tile - 16:9 picture, the length
bottom right, a warning top left, name and meta in mono, quality as a small badge.

The pictures are real where the design has gradients: a video's `large` still, a photo's
source, redirected to GoPro's CDN one row at a time as rows scroll into view. The
gradient stays underneath each one, and is all a tile gets when there is no picture.

Where it departs on purpose:

- **Switching tabs does not stop a cast.** The canvas drops `casting` on a tab change,
  which suits a mock-up; a real cast should not die because someone went to browse.
- **The "TV will refuse" flag shows only when the original is picked.** The canvas shows
  it on the one oversized sample; in a real library where all 48 videos are 3360p, and
  every tile opens on the proxy that plays, a flag on each would be noise saying
  something untrue. It appears once someone switches a tile to auto or original.
- **The text is English**, and since then so is the canvas: it was in Polish, and was
  translated (version 3 of the artifact) so the design and the page say the same things
  in the same words.
- **Photos in OneDrive are not listed yet.** The mirror holds 2420 JPGs, 28 GB, 609 of
  them only in the cloud, so they belong with the breadcrumb browsing the canvas also
  shows, not in one flat grid. Until then the Photos filter says so on that tab.
- **Clicking a photo still casts it.** In the canvas it selects the photo for a slideshow;
  that arrives with the slideshow itself, and a selection with nothing to start it would
  be a dead click.

Found on the way:

- **A token GoPro refuses for the list still works for everything on it.** A day-old
  token drew a 401 from `/media/search` while `/media/{id}/download` went on answering,
  so thumbnails loaded and a cast resolved. One "rejected" state had told a
  half-true story; there are two now, the tab says "token refused for the list" rather
  than "rejected", and the strip says what still works.
- **OneDrive placeholders.** 8 of the 18 videos exist only in the cloud. Those tiles say
  so, and nothing on the page reads a file merely to show it: a thumbnail would have made
  Windows download the whole file.

Left from the canvas, in the order proposed: the bottom bar that says what is playing and
holds Stop; selecting photos and the slideshow the laptop drives; browsing OneDrive by
folder, with its photos. The length and bit rate show once the list is refreshed with a
live token - the cache on this machine predates the `source_duration` fix.

## The cast bar

The panel that sat above the grid with the command's log is gone; the bar from the canvas
is pinned to the bottom instead. Idle, it says nothing is playing and whether a TV is
chosen. Casting, it carries the tile's picture, the name, a progress line and the time,
the tile's meta on the right, and Stop. The phases before playback are named - resolving
the address, handing it to the TV, starting on the TV - and the progress line pulses
rather than inventing a number until the TV has said how long the thing is.

The position is the TV's own. `cast-tv` already redraws `PLAYING 0:00:07.451 / 0:00:09`
every two seconds; the server keeps the last such line from the log, so the bar needs
no second channel to the TV.

The canvas has no state for a cast that did not play - it leaves that to the States
board - and the bar needs one. When the command's output contains one of the lines the
tools print on the way to giving up, the bar says "Did not play", quotes that line, and
"Why" opens the full log. It is read from the output rather than the exit status because
`cast-tv` exits 0 after "The TV never started playing", and a cast ended by Stop exits
with whatever the interrupt leaves (0xC000013A on Windows), so Stop is remembered and
reported as stopped instead. The log itself is not in the canvas either; it stays behind
the bar, because on the day something does not play, the reason is in it.

Testing the bar turned up a fault that was older than the bar. The log was read with
`read(256)` on a buffered pipe, which waits until it has all 256 bytes: at one 40-byte
status line every two seconds the output reached the page in bursts about twelve seconds
apart. The old panel looked live and was not, and a nine-second clip could play from start
to finish inside a single wait - the bar went from "resolving" straight to "finished".
The stand-in used to test this exited at once, and end of file flushes everything, so it
could not have shown it. `read1` hands over whatever has arrived; the bar now follows the
TV to the second: playing 1/9, 3/9, 5/9. It also showed that resolving takes about two
seconds, not the nine the bursts had suggested.

The first cast of the day went TRANSITIONING for forty seconds and gave up, and the same
clip played at once when tried again: the TV coming out of standby. The bar reported it as
it should - "Did not play", with the line - which is the state that exists for such a day.

## Selecting photos, and the slideshow

As the canvas has it: a photo tile carries a check, clicking it selects the photo instead
of casting it, the selection holds across tabs, and a video click casts at once and lets
the selection go. While anything is selected the bar is the picker - how many, "Clear
selection", "Change every 3 / 5 / 8 / 12 s" and "Start slideshow". The interval is
remembered in the browser.

**How the TV takes a series of stills was measured before anything was built.** Two of the
library's photos, handed over one after the other through `cast-tv`'s own server and SOAP:
the first went TRANSITIONING to PLAYING in about two seconds; over it, `SetAVTransportURI`
alone started the second - TRANSITIONING at once, PLAYING a second later - and the `Play`
sent after it was refused with UPnP 701, "Transition not available". Left alone, the second
stayed up for all thirty seconds it was watched. So a slide is one SOAP call, `Play` goes
only to a TV that reports STOPPED, and nothing has to be kept alive. (A still had seemed to
drop after about twelve seconds the day before; that was not the TV.)

**One server for the whole show.** The first idea, a `cast-tv` process per picture, would
have meant a new server and a new wait for every slide. Instead `cast-ui` loads `cast-tv` as
a module - as it already loads `cast-gopro` for thumbnails - keeps its server up on port 8895
for the length of the show, and points the TV at `/still/<show>-<n>.jpg` in turn, relayed
from GoPro's CDN. The next picture's address is fetched while the current one shows. The
queue and the countdown live in `cast-ui`, which is what the canvas's own note says: the
laptop drives the slideshow, because DLNA has no playlist.

The view is artboard Slideshow: what is on screen, name and meta, "3 / 8", the queue with the
current row marked, and at the bottom previous / pause / next, "Next in 5 s" with the next
name and a line counting down, the interval, and "End slideshow". When the queue runs out the
TV is stopped and returns to its own input, and the page says so with "Start over" - plus a
way back to the library, which the canvas does not draw but the page needs. The view is
rebuilt only when something in it changes; each second's tick moves the countdown and the
line and nothing else, so the pictures are not reloaded under the viewer's eyes.

A slideshow and a cast never run together - the TV plays one thing, and both want the port.
Starting a slideshow stops a running cast; starting a cast ends a running slideshow quietly,
without the "finished" screen.

Verified against the TV, through the page: three photos selected and started at 3 s and at
8 s; the pictures advancing on their own and the queue marking them; pause holding the
picture; a queue click and "previous" while paused; resume; "End slideshow"; "Start over";
the queue running out into "Slideshow finished"; "Back to the library". Through the API: ids
that are not photos of our own listing dropped rather than passed on; a cast started during
a show ending it quietly; a show started during a cast stopping it. Not verified: the layout
at phone width, which has rules but was not looked at.

Two faults found on the way. A picture jumped to while paused inherited what was left of
the one before it, so on resume it would have gone after a second; it gets its whole time
now. And selecting a tile redrew the grid, which reloads every picture - for a photo its
whole 3.6 MB source; a selection now changes the tile it is about and nothing else.

Not done, from the canvas: converting HEIC to JPEG on the fly, which the States board shows.
The standard library cannot decode HEIC and the tool has no dependencies; there are 3 HEIC
files in the OneDrive mirror today and the GoPro photos are JPEG, so it waits for a decision
about an outside decoder. OneDrive photos join the slideshow when OneDrive is browsed by
folder.

## OneDrive by folder, with photos

No Microsoft sign-in, by decision: on both machines the account is mirrored to disk, so
there is nothing to log in to for browsing. The gate the canvas draws would buy one thing
the disk cannot - thumbnails for files that exist only in the cloud - and the code is laid
out so that can be added later without touching a view.

**Browsing.** The mirror is opened a folder at a time under the canvas's breadcrumb, with
subfolders as tiles above the grid and their contents counted one level down; the tab's
hint names the folder that is open. Nothing reads a file's contents to list it - size,
date and whether it is a cloud-only placeholder all come with the directory entry. Photos
(JPEG, PNG) are listed with the videos and filtered by the same All / Videos / Photos;
HEIC is listed because it is there, marked because the TV cannot decode it, and does
nothing when clicked. Everything the page names in the mirror - a folder to open, a file
to cast or show, a thumbnail, a preview - goes through one function that refuses a path
leaving it.

**The thumbnail layer.** A provider has a cheap `can(item)`, run for every item of a folder
using only what the listing already knows, and a `serve(key)` that does the work only when
the browser asks. Each source has an ordered list of providers, and each listing gives
every item the address from the first that can serve it; the views render whatever address
they are handed, or keep the gradient. GoPro's stills moved behind the same door - the page
no longer builds `/api/gopro/thumb?id=` itself. A Microsoft Graph provider would go after
the EXIF one for "onedrive" and take the cloud-only files it refuses.

**EXIF previews,** measured on the mirror before the view was built: 1811 JPEGs on disk and
609 only in the cloud, which were never opened. Of 300 sampled from disk, 299 carry an
embedded preview - all 160 x 120, 8.9 KB at the median, about 3 ms to fetch from the first
128 KB. The one without was a non-camera JPEG in Documents. 36 of the 300 - one in eight -
were portrait shots whose previews lie on their side, because the orientation tag belongs
to the photo rather than its preview; turning JPEG pixels needs a decoder, so those are
served as an SVG that holds the preview turned. The previews are small and look soft on a
tile, which is what they cost: the alternative was the whole file.

**Cloud-only files.** A folder of 84 of them: 84 tiles marked "in the cloud", no image
elements, and no thumbnail requests at all. Casting one - a slideshow with one cloud-only
photo and one on disk - worked, the pictures went up in turn, and afterwards the listing
said the file was local and offered its preview: Windows had fetched it. The marker is read
from the file each time, not remembered.

**Mixed slideshows,** as the canvas's note says: two OneDrive photos and a GoPro one,
picked across tabs, played in order - OneDrive's straight off disk through the show's server,
GoPro's relayed - with the whole OneDrive photo, 5184 x 3888, as the page's preview.

**A fault in cast-tv this turned up.** A OneDrive video cast right after a slideshow ended
failed with "UPnP error 701, Transition not available": the TV, still busy with the last
picture, started the new address by itself on SetAVTransportURI and refused the Play after
it - the behaviour measured for slides. The slideshow already tolerated it; a single cast
did not. It does now, and the same cast played twice in a row where it had failed. On any
other answer to Play, nothing changed.

Also: two flags on one tile (HEIC and in the cloud, together) overlapped in the corner;
they stack now. And the canvas no longer promises "token · 2 h 14 min" - it says what the
page can know, "token working · stored 5 min ago" (artifact version 4).

Left, as agreed: the layout at phone width, and a fresh GoPro token for lengths and bit
rates, after this.

## Phone width

Checked at 390 x 780, the width of the canvas's Phone artboard, in a frame on the page's own
origin so the frame's width drove the media queries and the page inside could be inspected.
The browser window itself would not resize.

What was wrong: the page scrolled sideways on a phone - the three tabs with their hint lines
came to 402 px on a 390 px screen, Google Photos wrapping out past the edge. A filter row the
artboard does not have sat under the tabs, the token strip took two lines, and the idle bar
split into two.

What it does now, as the artboard has it: the header names the TV without its address; the
tabs are one segmented control with short names - GoPro, OneDrive, Photos - and no hint
line; two columns; and a bar with a thumb's room - "Tap to cast to the TV" centred when idle,
the count and a full-width "Start slideshow" when picking, a 54 x 32 picture, the name, the
line and a square 46 px Stop when playing. The Google Photos field and button are 46 px and
full width. The filters step aside on a phone, since the artboard has no row for them and
"Photos" there names the Google Photos tab.

Two things the artboard does not cover, decided here. The slideshow's controls, stacked under
the queue, sat a scroll away from pausing it; they stay pinned to the bottom, in two rows,
without the interval's label or the next picture's name, which have no room. And a "Log"
button stays in the bar, where the artboard has none, because the reason a cast did not play
is in it.

Also, everywhere: the page kept clear of the bar by a fixed 76 px, and a bar that says "Did
not play" and why is taller than that; it keeps clear of the bar's real height now, and of
nothing while the slideshow hides it. At full width nothing changed - long names, hints,
filters, six columns - which was checked after.
