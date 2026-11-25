---
change_id: s17-nextcloud
title: "Cast photos and videos from a Nextcloud server"
status: implementing
created: 2026-11-24
updated: 2026-11-25
archived_at: null
---

## Notes

cast photos and videos from a Nextcloud server: sign in with Login Flow v2 (no copied secrets), browse folders over WebDAV, cast like OneDrive. Owner decisions 2026-11-24: Nextcloud and the local-folder source are two separate changes, Nextcloud first; the local-folder change (later, s18) will allow only folders the owner adds, browsable only from the window or localhost, never from the phone.

2026-11-24: owner decision — fix every finding of reviews/impl-review-2253d5d.md (F1 Fix A); the Disconnect order is forget, then revoke; plan.md Definitions, Disconnect row.
2026-11-25: owner decision — Nextcloud films are downloaded before casting (OM films stall through the relay on Wi-Fi); plan.md Phase 5, row 3.9 n/a.
2026-11-25: reopened 4.2 — was accepted at 907f31c8f9fbe7f2f4116bda6d8d61f1dc9911a8; changed: README.md, context/foundation/prd.md
