# Review follow-ups: cloud-source-ui

## From the Phase 6 implementation review (2026-09-13)

- **Phase 7 — stale video directories on Windows.** `config.sweep_stale_video_dirs()` is
  POSIX-only: it proves a `cast-tv-videos-<pid>-*` directory orphaned with `os.kill(pid, 0)`,
  which on Windows would terminate the process. When Phase 7 moves paths to platformdirs, give
  Windows its own liveness check (e.g. `OpenProcess` via ctypes, or a lock file held by the
  owning process) or document that Storage Sense cleans `%TEMP%`.
  Source: `reviews/impl-review-phase-6.md`, F3 decision.
- **Manual re-check before the Phase 6 fixes are pushed.** Row 6.5 (a share link still plays)
  — **done 2026-09-13 22:23, played** (research.md, "Row 6.5 — re-check"); row 6.3 (a picked video, Original, downloads and plays) — **done 2026-09-13 22:27, played**
  (research.md, "Row 6.3 — re-check"): the share-link host allowlist and
  the download limits both touch these paths, and the real redirect chain of a share link was
  never catalogued.
  Source: `reviews/impl-review-phase-6.md`, F1 and F3 decisions.

## From the live re-check of row 6.5 (2026-09-13)

A share link to a **photo** was pasted (`photos.app.goo.gl/Nj2VHaD5bqKviYhq6`). The new host
allowlist resolved it (`=dv` on `lh3.googleusercontent.com` → `video-downloads.googleusercontent.com`),
but the photo is a motion photo: its `=dv` is the embedded clip (1.78 s HEVC 1440×1080 at 120 fps,
a second HEVC 2048×1536 still track, two data tracks; ffprobe). The scraper took it for a video
and the TV stayed `STOPPED` (`tv_never_started`). Share links are video-only by design
(`plan.md:995`, `plan.md:1376-1377`; `sharelink` probes with `kinds=("video",)`), so this is not a
regression. The known-good video link from row 6.5 (`KwhGzcxkNtQpudc46`) still resolves to the
same H.264 file.

- **A photo link should say so.** A motion photo passes as a video and ends in an opaque
  `tv_never_started`; a plain photo ends in `no_stream` ("they are probably stills"). Neither says
  that share links cast videos only. Tell the user plainly at paste time.
- **Photos (and motion-photo clips) through share links** — a new feature, not in the Phase 6
  plan: probe candidates with `kinds=("photo", "video")` and list a photo tile; for a motion
  photo's clip offer `=m37` (H.264 1080p) as a variant, as picked videos already do.
- **A GoPro hint on a Google Photos error.** `castlib/supervisor.py:312` appends "Try a lighter
  variant:  cast-gopro <n> -q proxy" to every `tv_never_started` hint, whatever the source; for
  Google Photos the lighter choice is the tile's "1080p stream" variant. (`castlib/cli.py:179`
  is the GoPro CLI and is right as it is.)
