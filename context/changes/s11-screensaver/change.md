---
change_id: s11-screensaver
title: Watch a slideshow or a long film without the TV's screen saver cutting in
status: implemented
created: 2026-09-20
updated: 2026-09-20
archived_at: null
---

## Notes

Roadmap slice S-11 (`context/foundation/roadmap.md`), phase:post-mvp, PRD ref US-03.

The owner's words: "Na TV pokazuje się wygaszacz w trakcie trwania slideshow, czy długiego
filmu - jak to obejść?" ("The TV shows its screen saver during a slideshow or a long film -
how do we get around it?")

Seen live on 2026-09-19 at about 23:05, during row 3.2 of `standalone-install` (its
`research.md` records it): a still HEIC photo was on the Samsung, the screen saver came on and
did not go away, while AVTransport still answered PLAYING and cast-tv showed no error. From our
side a covered screen and a playing one look identical - it read at first as a dead cast.

To find out before anything is planned: when exactly the Samsung starts it (idle time, photos
only or video too, paused versus playing) and whether a setting on the TV alone avoids it.

Ideas already on the roadmap: a periodic harmless key over Samsung's remote-control WebSocket
API (ports 8001/8002, needs a one-time pairing on the TV); a slideshow sent as one video stream
instead of single photos, so the TV sees playback.

## Decision, 2026-09-20: documented, not worked around

The owner's call after the measurement: **document the behaviour and close the slice; do not build
a workaround.** His words: "to zachowanie telewizora, nie luka w obecnej implementacji" ("this is
the TV's behaviour, not a hole in the current implementation").

What the measurement left on the table, and why each was declined:

- **The remote channel.** The one lever that works: a key press buys two minutes. It would mean a
  hand-written WebSocket client in a stdlib-only app, a pairing token, a TV menu setting that
  cannot be read remotely, and a real key press - with whatever it draws on screen - every hundred
  seconds for the length of a slideshow. The cost is visible to the person watching.
- **A slideshow encoded as video.** `frame.md` ruled this out because the saver was believed to
  cover a playing film as well; **the measurement overturned that** - a moving film survived six
  minutes. So the evidence against it is gone and only the cost stands: encoding video where the
  project's whole premise is that the TV pulls original bytes (`prd.md`, "no transcoding"). It is
  declined on that boundary, not on the old, now-false reason. If this is ever revisited, that is
  the ground to argue on, and the owner's own suggestion is a small prototype tested on the TV
  before any feature is built.
- **A TV setting.** There is none left: every configurable energy feature on the set is already off,
  and Samsung documents the OLED protection as non-disableable.

The outcome is a paragraph in README's Limitations, naming the two-minute timer, that a slideshow
does not reset it, that a paused film counts as a still picture, and that a nudge of the remote
brings the picture back without re-casting. `research.md` keeps the evidence.

**Revisit only if** the two-minute blanking turns out to block ordinary use - in which case the
first step is the prototype above, not a full feature.
