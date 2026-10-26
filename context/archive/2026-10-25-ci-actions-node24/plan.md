# Move the workflows' GitHub actions off Node.js 20 Implementation Plan

## Overview

GitHub runs actions that target Node.js 20 on Node.js 24 and warns that they are deprecated.
cast-tv's two workflows pin six actions; every pinned major targets Node.js 20 or older. This
plan moves each pin to the newest major, all of which declare `runs.using: node24`.

## Current State Analysis

The pins at planning (`grep -hoE "uses: actions/[a-z-]+@v[0-9]+" .github/workflows/*.yml`):

| File:line | Pin | `runs.using` of that major |
| --- | --- | --- |
| `.github/workflows/test.yml:16` | `actions/checkout@v4` | `node20` |
| `.github/workflows/test.yml:17` | `actions/setup-python@v5` | `node20` |
| `.github/workflows/release.yml:26` | `actions/checkout@v4` | `node20` |
| `.github/workflows/release.yml:27` | `actions/setup-python@v5` | `node20` |
| `.github/workflows/release.yml:69` | `actions/upload-artifact@v4` | `node20` |
| `.github/workflows/release.yml:82` | `actions/download-artifact@v4` | `node20` |

Each action's `action.yml` at its major tag, read with `gh api repos/actions/<name>/contents/action.yml?ref=<tag>`
on 2026-10-26:

- `checkout`: v4 `node20`; v5, v6, v7 `node24`. Latest release v7.0.1 (2026-07-20).
- `setup-python`: v5 `node20`; v6, v7 `node24`. Latest release v7.1.0 (2026-10-22).
- `upload-artifact`: v4, v5 `node20`; v6, v7 `node24`. Latest release v7.0.2 (2026-10-07).
- `download-artifact`: v4, v5, v6 `node20`; v7, v8 `node24`. Latest release v8.0.2 (2026-10-07).

The breaking changes between today's pins and the newest majors, from the release notes of each
major's first release (read 2026-10-26), and why none applies here:

- **checkout v6**: credentials persist to a separate file. Neither workflow runs `git` with the
  checkout's credentials after the checkout step; the release job uses `gh` with `github.token`.
- **checkout v7**: refuses to check out a fork's PR under `pull_request_target` and `workflow_run`.
  Neither workflow uses those events.
- **setup-python v6/v7**: needs runner 2.327.1 or later (GitHub-hosted runners qualify); v7
  removed the `pip-install` input, which neither workflow sets.
- **upload-artifact v6/v7**: Node 24; v7 adds `archive: false` (not used, so uploads stay zipped).
- **download-artifact v7/v8**: Node 24; v8 errors on a digest mismatch by default and unzips only
  zipped artifacts. The release job downloads the two zipped artifacts the build uploaded, with
  `merge-multiple: true` (`release.yml:82-85`).

`release.yml` runs on a pull request that touches it (`release.yml:9-12`), so the PR exercises
`checkout`, `setup-python` and `upload-artifact` on both runners. The `release` job, the only user
of `download-artifact`, runs on a `v*` tag only (`release.yml:77`).

### Carried from predecessor

none — no Predecessor line

## Definitions

Ledger: no domain terms beyond "runs on Node.js 24", which means the action's `action.yml`
declares `runs.using: node24` at the pinned major tag; nothing to define.

## Desired End State

Both workflows pin `actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7`
and `actions/download-artifact@v8`. The PR's test and release-build runs are green on both
operating systems and show no Node.js 20 deprecation annotation. The next `v*` tag publishes a
release with both files through the new `download-artifact`.

## What We're NOT Doing

- **No pinning to commit SHAs.** The workflows pin major tags today and keep doing so (assumed
  without asking: the repository's existing convention).
- **No trial tag to exercise the `release` job now** (owner, 2026-10-26: "Przy następnym tagu").
  It is a manual row checked at the next real tag.
- **No other workflow change**: Python 3.12, the runner images and the steps stay as they are.
- **Not the ai-toolkit repository's `ci-actions-node24`**, a separate change there.

## Implementation Approach

One phase: change the six pins, open the PR, let both workflows run on it.

## Phase 1: The pins move to the Node.js 24 majors

### Overview

Every `uses: actions/…` line in the two workflows names a major whose `action.yml` runs on
`node24`.

### Changes Required:

#### 1. The workflows

**Files**:
- `.github/workflows/test.yml` lines 16-17: `checkout@v4` → `@v7`, `setup-python@v5` → `@v7`.
- `.github/workflows/release.yml` lines 26-27, 69, 82: `checkout@v4` → `@v7`, `setup-python@v5` →
  `@v7`, `upload-artifact@v4` → `@v7`, `download-artifact@v4` → `@v8`.

**Intent**: Move off the deprecated Node.js 20 runtime, to the newest majors (owner, 2026-10-26).

**Contract**: only the version after `@` changes; every `with:` input stays (`python-version`,
`name`, `path`, `if-no-files-found`, `merge-multiple`).

### Success Criteria:

#### Automated Verification:

- The pins are exactly the four new ones (2× `checkout@v7`, 2× `setup-python@v7`, 1× `upload-artifact@v7`, 1× `download-artifact@v8`), and no other `actions/` pin remains: `grep -hoE "uses: actions/[a-z-]+@v[0-9]+" .github/workflows/*.yml | sort | uniq -c` — at planning: exit 0 — prints the six old pins until Phase 1
- The test workflow on the PR is green on `ubuntu-latest` and `windows-latest` (pyflakes and the full suite): `gh pr checks <pr>` — not run: external
- The release workflow on the PR builds and smoke-tests both files, and neither the test nor the release run carries a Node.js 20 deprecation annotation: `gh pr checks <pr>`, then `gh api repos/Piotr-Miller/cast-tv/check-runs/<job id>/annotations` for each job — not run: external

#### Manual Verification:

- At the next `v*` tag (for example `v0.5.0-rc1` after S-12), the release run's `release` job downloads both artifacts with `download-artifact@v8` and the GitHub release lists `cast-tv-windows-x64.exe` and `cast-tv-linux-x64` at the sizes the build printed — surface: .github/workflows/release.yml

**Implementation Note**: the manual row waits for a tag the owner decides on; the change may be
archived with it pending, recorded as pending acceptance.

---

## Testing Strategy

### Unit Tests:

- None: no Python changes.

### Integration Tests:

- Both workflows on the PR (test on two OSes, release build and smoke test on two OSes).

### Manual Testing Steps:

1. At the next `v*` tag: the `release` job is green, and the GitHub release has both files.

## References

- `context/changes/ci-actions-node24/change.md` (the six pins at creation)
- Release notes: https://github.com/actions/checkout/releases, https://github.com/actions/setup-python/releases, https://github.com/actions/upload-artifact/releases, https://github.com/actions/download-artifact/releases (read 2026-10-26)
- Lessons applied: 2 of 6 entries in `context/foundation/lessons.md` (branches first; a manual step names where to act)

## Progress

> Convention: `- [ ]` pending, `- [x]` done, `- [-]` not applicable (` — n/a: <reason>` required). Append ` — <commit sha>` when a step lands. A Manual row takes ` — accepted at <full sha>` when a human confirms it. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: The pins move to the Node.js 24 majors

#### Automated

- [x] 1.1 The pins are exactly the four new ones — 1185659
- [x] 1.2 The test workflow on the PR is green on both OSes — 1185659
- [x] 1.3 The release workflow on the PR is green, with no Node.js 20 annotation — 1185659

#### Manual

- [ ] 1.4 The next tag's release job publishes both files
