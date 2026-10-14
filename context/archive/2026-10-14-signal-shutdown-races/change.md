---
change_id: signal-shutdown-races
title: "Make the SIGTERM and SIGINT subprocess tests reliable on Ubuntu CI"
status: archived
outcome: completed
created: 2026-10-14
updated: 2026-10-14
archived_at: 2026-10-14T20:58:57Z
archive_commit: febfded
sync: none
---

## Notes

flaky Ubuntu CI: the SIGTERM and SIGINT subprocess tests race the app's startup and shutdown
2026-10-14: reopened 3.6 — was accepted at bed2488c3c4db64fed700caaaca84f2e0db751cf; changed: castlib/app.py (impl-review F1 fix)
2026-10-14: reopened 3.7 — was accepted at bed2488c3c4db64fed700caaaca84f2e0db751cf; changed: castlib/app.py (impl-review F1 fix)
2026-10-14: reopened 3.8 — was accepted at bed2488c3c4db64fed700caaaca84f2e0db751cf; changed: castlib/app.py (impl-review F1 fix)
2026-10-14: owner decision — Ctrl+C before the HTTP loop runs closes only the socket; cast/show serve() before their try (impl-review F1, F3); plan.md Definitions, Critical Implementation Details
2026-10-14: owner decision — the SIGTERM test child prints ready and runs run_forever inside cli.ui's KeyboardInterrupt fallback (impl-review F2); plan.md Desired End State
2026-10-14: owner decision — PR #53 merged by rebase (7315e22), so Progress rows are remapped to the main commits with identical trees: e39716a → 881a565 (p1), 4cdcfbd → f60d99a (p2), 0e33b39 → 23111dd (p3), acceptance 89a1005 → dfdb032; plan.md Progress. Branch → main for the other commits: 5c7ad02 → bc21ead, bed2488 → 73e3c8e, c52188c → b7e5a83, e7173ec → 54704ea, 3531511 → af8bd5c, 83d2629 → 7315e22
