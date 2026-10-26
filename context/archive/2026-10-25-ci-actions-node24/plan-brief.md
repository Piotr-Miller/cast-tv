# Move the workflows' GitHub actions off Node.js 20 — Plan Brief

> Full plan: `context/changes/ci-actions-node24/plan.md`

## What & Why

GitHub forces actions that target Node.js 20 onto Node.js 24 and flags them as deprecated.
cast-tv's test and release workflows pin six actions, all on Node.js 20 majors. This change moves
them to majors that declare `runs.using: node24`.

## Starting Point

`test.yml` pins `checkout@v4` and `setup-python@v5`; `release.yml` pins those two plus
`upload-artifact@v4` and `download-artifact@v4`. Every one of those majors runs on `node20`.

## Desired End State

Both workflows pin `checkout@v7`, `setup-python@v7`, `upload-artifact@v7` and
`download-artifact@v8`. The PR's runs are green on both OSes without a Node.js 20 annotation,
and the next tag publishes a release through the new `download-artifact`.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Which majors | The newest: checkout v7, setup-python v7, upload-artifact v7, download-artifact v8 | Longest until the next migration; none of their breaking changes touches these workflows (owner, 2026-10-26). |
| Proving the `release` job | At the next real `v*` tag, as a manual row | A PR never runs that job, and a trial tag would publish a public pre-release (owner, 2026-10-26). |
| Pin style | Major tags, as today | The repository's convention; assumed without asking. |

## Scope

**In scope:** the six `uses: actions/…` pins in `.github/workflows/test.yml` and `release.yml`.

**Out of scope:** SHA pinning, a trial tag, any other workflow change, the ai-toolkit repository's
own `ci-actions-node24`.

## Architecture / Approach

Change only the version after `@`; keep every `with:` input. The PR runs both workflows, since
`release.yml` changes; the tag-only `release` job is checked by hand at the next tag.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. The pins move to the Node.js 24 majors | Six pins updated; PR green on both OSes | `download-artifact@v8` is unproven until a tag runs the `release` job |

**Prerequisites:** none.
**Estimated effort:** one short session, plus one manual check at the next tag.

## Open Risks & Assumptions

- `download-artifact@v8` errors on a digest mismatch and unzips only zipped artifacts; the build
  uploads zipped artifacts, so this should hold, but only the next tag proves it.
- The majors are ESM rewrites released in 2026; GitHub-hosted runners meet their runner floor
  (2.327.1).

## Success Criteria (Summary)

- No Node.js 20 deprecation annotation on the PR's test and release-build runs.
- The next tag's release lists both files.
