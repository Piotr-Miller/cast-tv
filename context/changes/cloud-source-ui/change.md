---
change_id: cloud-source-ui
title: Pick media from GoPro, Google Photos and OneDrive in a UI, and cast it
status: new
created: 2026-09-07
updated: 2026-09-07
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
