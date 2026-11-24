---
change_id: s17-nextcloud
title: "Cast photos and videos from a Nextcloud server"
status: impl_reviewed
created: 2026-11-24
updated: 2026-11-24
archived_at: null
---

## Notes

cast photos and videos from a Nextcloud server: sign in with Login Flow v2 (no copied secrets), browse folders over WebDAV, cast like OneDrive. Owner decisions 2026-11-24: Nextcloud and the local-folder source are two separate changes, Nextcloud first; the local-folder change (later, s18) will allow only folders the owner adds, browsable only from the window or localhost, never from the phone.

2026-11-24: owner decision — fix every finding of reviews/impl-review-2253d5d.md (F1 Fix A); the Disconnect order is forget, then revoke; plan.md Definitions, Disconnect row.
