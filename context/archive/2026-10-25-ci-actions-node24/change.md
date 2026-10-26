---
change_id: ci-actions-node24
title: "Move the workflows' GitHub actions off Node.js 20"
status: archived
outcome: completed
created: 2026-10-25
updated: 2026-10-26
archived_at: 2026-10-26T20:58:49Z
---

## Notes

GitHub forces actions that target Node.js 20 onto Node.js 24 with a deprecation notice. The same follow-up is open
in `@piotr-miller/ai-toolkit` as its own change, `ci-actions-node24`; this one covers only cast-tv's workflows.

At creation: 6 pins in 2 workflows — `test.yml:16` `actions/checkout@v4`, `test.yml:17` `actions/setup-python@v5`,
`release.yml:26` `actions/checkout@v4`, `release.yml:27` `actions/setup-python@v5`, `release.yml:45`
`actions/upload-artifact@v4`, `release.yml:58` `actions/download-artifact@v4`. Which majors run on Node.js 24 is to
be checked at planning (each action's `action.yml`, `runs.using`). lumina-clean-ai already uses `checkout@v5`,
`setup-node@v5`, `cache@v5` and `upload-artifact@v7`.

`release.yml` is release infrastructure: its change is fully proven only by the next real release run.

2026-10-26: owner decisions — the newest majors (checkout v7, setup-python v7, upload-artifact v7, download-artifact v8); the `release` job is checked at the next real tag, not a trial one; plan.md Overview, What We're NOT Doing

2026-10-26: PR #82 squash-merged as 1185659 on main; Progress rows 1.1-1.3 rewritten from f9b6beb. Impl review APPROVED, 0 findings (reviews/impl-review-1b92d0c.md); 1.4 pending the next v* tag.
