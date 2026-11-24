# Phase 1 implementation-review fixes

Source: `reviews/impl-review-phase-1-e931d9e.md`, F1–F5.
Owner approved all recommended fixes on 2026-11-24. All are applied locally; this review does not commit.

- F1: invalidate pending sign-in starts on Cancel/Disconnect/close; fix the OneDrive and Google Photos sibling starts.
- F2: guard Nextcloud DAV/cache/page/preview/deferred-media results against account changes; guard OneDrive and GoPro sibling cache writes and OneDrive deferred resolution.
- F3: atomically adopt a verified credential/user id; guard OneDrive sibling verification/account updates and Nextcloud late revoke cleanup.
- F4: turn malformed typed addresses into validation errors; make the shared origin helper fail closed.
- F5: apply first-file-id deduplication across folder/media entries.

## Files for the next implementation commit

- `castlib/auth/loginflow.py`
- `castlib/net.py`
- `castlib/sources/nextcloud.py`
- `castlib/sources/onedrive.py`
- `castlib/sources/gphotos.py`
- `castlib/sources/gopro.py`
- `tests/test_nextcloud.py`
- `tests/test_source_races.py`
- `tests/test_gopro.py`
- `context/changes/s17-nextcloud/reviews/impl-review-phase-1-e931d9e.md`
- `context/changes/s17-nextcloud/follow-ups/review-fixes.md`
- `context/changes/s17-nextcloud/change.md` (workflow stamp; content already has today's date)

The existing local `plan.md` SHA write-back and later row 1.4 update were not edited by this review.
No Manual row was confirmed or reopened. All implementation-review findings are fixed; later plan phases remain pending.

## Validation

- Affected-source suite: 222 passed, with unhandled thread exceptions treated as failures.
- Full suite: 737 passed, 6 skipped, with unhandled thread exceptions treated as failures.
- `python -m pyflakes castlib tests`: exit 0.
- `git diff --check`: exit 0.
- The original Phase 1 commit's release build and smoke test passed on Windows and Linux; this does not certify the uncommitted fixes in CI.
