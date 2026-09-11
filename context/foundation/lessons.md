# Lessons Learned

> Append-only register of recurring rules and patterns. Re-read at start by /10x-frame, /10x-research, /10x-plan, /10x-plan-review, /10x-implement, /10x-impl-review.

## A ticked manual row needs a written observation

- **Context**: the `Manual` rows under `## Progress` in `context/changes/<change-id>/plan.md`. First seen in the cloud-source-ui Phase 1 review (F7); again in the Phase 3 review (F9: rows 3.3, 3.5 and 3.7 ticked at `57d012f` with only the commit SHA), recorded 2026-09-11.
- **Problem**: manual rows were ticked with the phase commit and nothing else, so a reviewer could not tell an exercised row from a rubber-stamped one, and the evidence had to be reconstructed a day later from memory.
- **Rule**: before ticking a manual row, write in `research.md`: the row number, the date it was run, the device or material, and the result actually observed. The reviewer checks the note against the criterion. No note means the row stays open; neither the commit nor a passing automated test stands in for the manual observation.
- **Applies to**: `/10x-implement` when it ticks Progress rows; `/10x-impl-review` in the Success Criteria check; every manual row in every plan.

