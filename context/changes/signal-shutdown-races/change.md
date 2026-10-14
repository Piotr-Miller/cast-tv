---
change_id: signal-shutdown-races
title: "Make the SIGTERM and SIGINT subprocess tests reliable on Ubuntu CI"
status: implementing
created: 2026-10-14
updated: 2026-10-14
archived_at: null
---

## Notes

flaky Ubuntu CI: the SIGTERM and SIGINT subprocess tests race the app's startup and shutdown
