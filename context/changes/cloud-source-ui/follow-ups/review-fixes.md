# Review follow-ups: cloud-source-ui

## From the Phase 6 implementation review (2026-09-13)

- **Done in Phase 7 (`7a7c885`), marked 2026-09-19.** ~~Phase 7 — stale video directories on
  Windows.~~ `config.sweep_stale_video_dirs()` asks `OpenProcess` whether the owning pid lives on
  Windows instead of `os.kill(pid, 0)`, and skips the ownership check there (`%TEMP%` is per user).
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

- **Done 2026-09-19.** ~~A photo link should say so.~~ A share page names what it shares: a
  video's carries `og:video` tags, a photo's - a motion photo's too - only `og:image` (the two
  real links of row 6.5 compared). `sharelink.resolve()` now reads that before any probe and
  answers `photo_link`: share links cast videos only, pick the photo in Google's picker. A page
  with neither tag is probed as before, and `no_stream` says the same about photos. Checked on
  the real links: the motion photo gets `photo_link`, the video still resolves to `=dv`.
- **Photos (and motion-photo clips) through share links** — a new feature, not in the Phase 6
  plan: probe candidates with `kinds=("photo", "video")` and list a photo tile; for a motion
  photo's clip offer `=m37` (H.264 1080p) as a variant, as picked videos already do.
- **Done 2026-09-19.** ~~A GoPro hint on a Google Photos error.~~ `supervisor.lighter_hint()`
  names the lighter variant the item's source has: GoPro's Proxy (with `cast-gopro <n> -q proxy`),
  a picked Google Photos video's 1080p stream, the picker for a share link (which has no variant),
  and no variant for OneDrive and local files. `castlib/cli.py` printed the GoPro line for every
  source too - it serves `cast-tv` and `cast-photos` as well - and now prints the same hint.

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

- **Done 2026-09-19.** ~~The firewall hint misleads on a managed Windows machine.~~ An MDM's
  inbound block-all rule (`Block InBound connection Public Private`, every filter `Any`) outranks
  any allow rule, so the `netsh` hint could not help. `platform.FirewallPolicy` now asks the active
  store once, in the background (PowerShell, no administrator rights; about 6 s on this laptop),
  for an enabled inbound Block rule covering TCP on any port, program and address for a current
  network profile. When there is one, the banner warns, `tv_fetched_nothing` says that the
  organisation's policy blocks incoming connections and casting from this computer is not
  possible, and the UI shows that instead of the command; otherwise the `netsh` line stays, now
  marked as needing an administrator PowerShell. Checked here: the query answers
  `{"profiles":["Public"],"rules":[]}` (the same query on Allow rules lists them, so it reads the
  store); the blocked path with the managed laptop's rule, simulated. Not tried on a managed
  laptop itself.
  Source: `research.md`, "Row 7.3 — first attempt, a managed Windows laptop".

## From manual row 7.3, second attempt (2026-09-18)

- **Done 2026-09-19 (PR #11, `106d76e`).** ~~Closing the console window skips the clean shutdown
  on Windows.~~ `CTRL_CLOSE_EVENT` is not a `KeyboardInterrupt` to Python, so closing the window
  ended the process without `Stop`, `close()` or `atexit`; mid-film the TV showed a broken-stream
  error (Piotr's recollection, not the exact wording). `platform.ConsoleClose` now handles close,
  logoff and shutdown: it interrupts the main thread, so the Ctrl+C path runs, and waits out
  Windows' grace. Checked on the Samsung with one photo, the window closed with `WM_CLOSE` to a
  classic console: `main`'s build died in 0.1 s and the photo stayed up (`PLAYING`) - so without
  the fix a photo does stay, which was open here - while the fixed build printed `Stopped.`,
  exited in 0.6 s and the TV answered `STOPPED`. Windows Terminal too: after `pipx reinstall
  cast-tv` from `main`, Piotr cast one photo and closed the Windows Terminal window with X; the photo
  left the TV within about a second, the TV then answered `STOPPED` and no `cast-tv` was left.
  Source: `research.md`, "Row 7.3 — second attempt, an unmanaged Windows laptop".
