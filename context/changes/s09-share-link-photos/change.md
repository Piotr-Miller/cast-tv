---
change_id: s09-share-link-photos
title: "Cast a photo or a motion photo's clip from a share link"
status: impl_reviewed
created: 2026-10-13
updated: 2026-10-14
archived_at: null
---

## Notes

cast a photo or a motion photo's clip from a share link
- 2026-10-13: owner decision — a network failure or timeout on the `=d` probe raises `probe_failed`; an HTTP error or non-photo answer there is `no_media`; plan.md Phase 1, Changes Required §1
- 2026-10-14: PR #50 merged by rebase, so every branch commit has a new SHA on main with an identical tree (`git diff <branch> <main>` empty for each). Owner decision: the Progress suffixes in plan.md name the main commits. Map, branch → main: `aed13dc` → `d91f871` (p1), `9111645` → `a74a1bc` (p2), `2c1c9f5` → `413773c` (p3), `17b54ef` → `9afd432` (epilogue; the head of `reviews/impl-review-17b54ef.md`), `eb50aae` → `d862414` (fix), `f3ab375` → `5294020` (rows 3.3-3.8 accepted; TV build per research.md), `b938000` → `5cd7cd4`, `7ec6e6a` → `3366f69`, `973249d` → `c9942e5`. The review reports and research.md keep the branch SHAs they were written with.
