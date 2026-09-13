# Review follow-ups: cloud-source-ui

## From the Phase 6 implementation review (2026-09-13)

- **Phase 7 — stale video directories on Windows.** `config.sweep_stale_video_dirs()` is
  POSIX-only: it proves a `cast-tv-videos-<pid>-*` directory orphaned with `os.kill(pid, 0)`,
  which on Windows would terminate the process. When Phase 7 moves paths to platformdirs, give
  Windows its own liveness check (e.g. `OpenProcess` via ctypes, or a lock file held by the
  owning process) or document that Storage Sense cleans `%TEMP%`.
  Source: `reviews/impl-review-phase-6.md`, F3 decision.
- **Manual re-check before the Phase 6 fixes are pushed.** Row 6.5 (a share link still plays)
  and row 6.3 (a picked video, Original, downloads and plays): the share-link host allowlist and
  the download limits both touch these paths, and the real redirect chain of a share link was
  never catalogued.
  Source: `reviews/impl-review-phase-6.md`, F1 and F3 decisions.
