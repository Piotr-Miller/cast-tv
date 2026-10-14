# Implementation review fixes

## F1 — Clip probe accepts unsupported success statuses

- **Review**: ../reviews/impl-review-phase-1-aed13dc.md
- **Decision**: owner selected Fix now, 2026-10-13.
- **Status**: applied and verified; committed with phase 2 in `9111645` on the branch, `a74a1bc` on main.
- **Files**: castlib/sources/sharelink.py, tests/test_gphotos.py.
- **Result**: accept only 200/206 video responses; reject 202/204 for video/mp4 and application/mp4 with status/type diagnostics. Valid 200/206 clips remain supported.
- **Verification**: four new regressions failed before the fix; after the fix, 23 classification cases passed, the suite reported 362 passed and 1 skipped, Pyflakes and git diff --check were clean.
- **Siblings**: no other clip detector found. The general media probe and relay MIME fallback have different contracts and were left unchanged.
- **Manual acceptance reopened**: none; all existing Manual rows remain pending.
