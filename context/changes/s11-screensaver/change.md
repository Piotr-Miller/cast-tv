---
change_id: s11-screensaver
title: Watch a slideshow or a long film without the TV's screen saver cutting in
status: preparing
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
