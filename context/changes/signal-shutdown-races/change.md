---
change_id: signal-shutdown-races
title: "Make the SIGTERM and SIGINT subprocess tests reliable on Ubuntu CI"
status: impl_reviewed
created: 2026-10-14
updated: 2026-10-14
archived_at: null
---

## Notes

flaky Ubuntu CI: the SIGTERM and SIGINT subprocess tests race the app's startup and shutdown
2026-10-14: reopened 3.6 — was accepted at bed2488c3c4db64fed700caaaca84f2e0db751cf; changed: castlib/app.py (impl-review F1 fix)
2026-10-14: reopened 3.7 — was accepted at bed2488c3c4db64fed700caaaca84f2e0db751cf; changed: castlib/app.py (impl-review F1 fix)
2026-10-14: reopened 3.8 — was accepted at bed2488c3c4db64fed700caaaca84f2e0db751cf; changed: castlib/app.py (impl-review F1 fix)
2026-10-14: owner decision — Ctrl+C before the HTTP loop runs closes only the socket; cast/show serve() before their try (impl-review F1, F3); plan.md Definitions, Critical Implementation Details
2026-10-14: owner decision — the SIGTERM test child prints ready and runs run_forever inside cli.ui's KeyboardInterrupt fallback (impl-review F2); plan.md Desired End State
