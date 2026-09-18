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

## From manual row 4.6 (2026-09-15)

- **Done 2026-09-15 (plan addendum, Phase 7).** ~~A 701 on `SetAVTransportURI` fails the newer cast; the older one keeps the TV.~~ Two casts
  within a second (a double tap on the phone): the first went out and played; the second's
  `SetAVTransportURI` reached the Samsung while it was `TRANSITIONING` and was refused with UPnP
  701, and `Cast.run` ends such a cast as `tv_rejected` at once (`castlib/supervisor.py`, the
  `except` around `SetAVTransportURI`; only a 701 on `Play` gets the `_settles_playing` window).
  That breaks the plan's `cast (while playing)` rule, "the request accepted second wins", and
  shows an error for a cast the user can see playing (the same clip here). Likely fix: on a 701
  from `SetAVTransportURI`, wait for the transport to leave `TRANSITIONING` (bounded, as
  `PLAY_701_GRACE`) and send `SetAVTransportURI` once more, provided the cast is still current;
  plus a scripted-fake test where the FakeTV answers 701 to a `SetAVTransportURI` during
  `TRANSITIONING`. Also worth debouncing the UI's Cast button while a cast request is in flight.
  Source: `research.md`, "Row 4.6 — second attempt".

## From manual row 7.3, first attempt (2026-09-17)

- **The firewall hint misleads on a managed Windows machine.** `tv_fetched_nothing` hints
  `netsh advfirewall firewall add rule … action=allow …`, but on a laptop whose MDM pushes an
  inbound block-all rule (`Block InBound connection Public Private`, every filter `Any`) no allow
  rule can win, and `netsh` needs administrator rights the user may not have. The diagnosis itself
  was right. Possible fix: on Windows, when an enabled inbound Block rule with no port or program
  filter is active for the current profile (`Get-NetFirewallRule -PolicyStore ActiveStore`), say
  that the organisation's policy blocks incoming connections and that casting from this machine is
  not possible; otherwise keep the `netsh` line, noting it needs an administrator prompt.
  Source: `research.md`, "Row 7.3 — first attempt, a managed Windows laptop".

## From manual row 7.3, second attempt (2026-09-18)

- **Closing the console window skips the clean shutdown on Windows.** Closing the window is how
  many Windows users end a program, and it delivers `CTRL_CLOSE_EVENT`, which Python does not turn
  into `KeyboardInterrupt`: the process is ended without `Stop` to the TV, without `atexit` (the
  photo and video temp directories stay until a later run reclaims them) and without `close()` on
  the sources (Google Photos picker sessions are not deleted). A streaming video stops by itself
  when the connection drops; a photo stays on the TV. Possible fix: on Windows, register a handler
  with `SetConsoleCtrlHandler` that runs the same path as Ctrl+C for `CTRL_CLOSE_EVENT`,
  `CTRL_LOGOFF_EVENT` and `CTRL_SHUTDOWN_EVENT`, within the roughly 5 s Windows allows.
  Source: `research.md`, "Row 7.3 — second attempt, an unmanaged Windows laptop".
