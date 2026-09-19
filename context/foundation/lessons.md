# Lessons Learned

> Append-only register of recurring rules and patterns. Re-read at start by /10x-frame, /10x-research, /10x-plan, /10x-plan-review, /10x-implement, /10x-impl-review.

## A ticked manual row needs a written observation

- **Context**: the `Manual` rows under `## Progress` in `context/changes/<change-id>/plan.md`. First seen in the cloud-source-ui Phase 1 review (F7); again in the Phase 3 review (F9: rows 3.3, 3.5 and 3.7 ticked at `57d012f` with only the commit SHA), recorded 2026-09-11.
- **Problem**: manual rows were ticked with the phase commit and nothing else, so a reviewer could not tell an exercised row from a rubber-stamped one, and the evidence had to be reconstructed a day later from memory.
- **Rule**: before ticking a manual row, write in `research.md`: the row number, the date it was run, the device or material, and the result actually observed. The reviewer checks the note against the criterion. No note means the row stays open; neither the commit nor a passing automated test stands in for the manual observation.
- **Applies to**: `/10x-implement` when it ticks Progress rows; `/10x-impl-review` in the Success Criteria check; every manual row in every plan.


## Look at every branch and PR before building

- **Context**: the cast-tv UI, 2026-09-18. The reviewed, tested implementation sat on the branch `shape-the-cloud-source-ui` (PR #1) while another session built a second UI on `main` (PRs #2-#8).
- **Problem**: nobody looked at the remote branches first; the duplicate was reverted in PR #9 and a session was lost.
- **Rule**: before implementing anything, `git fetch`, then read `git branch -r`, `gh pr list` and the `plan.md` of every folder under `context/changes/`. Branch new work from an up-to-date `main`, never from the branch of an open PR.
- **Applies to**: the start of every session and every new change; `/10x-implement`.

## A step for the person names exactly where to act

- **Context**: manual rows and follow-up checks run by the owner. Row 7.3 (2026-09-18): "press Ctrl+C" without saying it goes in the PowerShell window running cast-tv, not the browser UI. 2026-09-19: "paste the share link into the UI", when the field only appeared after Connect, which that laptop could not do.
- **Problem**: each vague step cost a round of testing and a screenshot to find out what the person saw.
- **Rule**: every manual step names the window or page, the control and what the person should then see ("in the PowerShell window running cast-tv, press Ctrl+C; it prints `Stopped.`"). Before handing a UI step over, check the control is reachable from the state the person is in.
- **Applies to**: manual rows in every plan; any test the owner runs.

## Nothing the app needs is a file the user copies

- **Context**: `standalone-install`, 2026-09-19. Google Photos' Connect answered "no Google OAuth client is configured" and told the user to create a Google Cloud project and copy its JSON. The owner: "situation when we need to copy some kind of files to make app working is out of the question".
- **Problem**: a setup step outside the app reads as a defect to the user, and on a new PC it makes a whole source unusable.
- **Rule**: credentials and settings the app needs ship with it (OneDrive's `DEFAULT_CLIENT_ID`; the release's built-in Google client); files and environment variables may only override. A missing-config error never answers "copy this file". Steps inside the UI (a consent page, a pasted token) are fine.
- **Applies to**: `/10x-plan` when a feature needs a credential or setting; error messages.

## A provider secret never enters the public repository

- **Context**: shipping the Google Desktop client (`standalone-install`, 2026-09-19). Google calls a desktop client's secret non-confidential, but GitHub push protection blocks Google secrets, and a secret found in a public repo is reported to Google.
- **Problem**: a committed secret can be revoked for every installed copy at once.
- **Rule**: a secret goes into GitHub Actions repository secrets and is written into the build by the release workflow (`packaging/write_client.py`); the source tree carries a stub. The owner enters secret values; the agent never reads or prints them (the same holds for the GoPro token).
- **Applies to**: any new third-party client, key or token.

## A message from a user action is not owned by the status poll

- **Context**: PR #16, 2026-09-19. The share-link error was written to `pickNote`, which `watchPicks()` resets on every `/api/status` poll (every 1.5 s).
- **Problem**: the error the user needed ("that link is to a photo") would vanish within 1.5 s of appearing on a connected tab, and PR #16's status change would have done the same on the gate. Found by reading the code while writing #16, not by a user losing the message.
- **Rule**: a message set in answer to something the user did gets its own state (`linkNote`), cleared only by that action's next attempt; the poll may only write messages derived from server state.
- **Applies to**: `castlib/ui/app.js`; any polled UI.
