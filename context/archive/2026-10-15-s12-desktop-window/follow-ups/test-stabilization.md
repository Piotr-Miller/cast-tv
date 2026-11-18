# Existing intermittent tests — separate follow-up

Recorded during Phase 1 implementation-review triage on 2026-10-18. These are future stabilization candidates, not implementation work authorized by this change. The final combined F1/F2 full suite passed with both tests included (431 passed, 5 skipped, exit 0, 110.20s); earlier failures remain in reviews/impl-review-phase-1-1083431.md.

## CLI initialization synchronization

- Test: tests/test_cli.py::test_cast_replaced_from_the_ui_keeps_serving.
- Observed failure: AttributeError at tests/test_cli.py:124 while polling servers[0].app.current.
- Evidence: App.__init__ publishes server.app before initializing current. The same publication order and test predicate exist at the phase base revision.
- Future investigation: make the test wait for a fully initialized App, or define a deliberate ready-publication boundary. Keep this separate from the shutdown fixes and verify the synchronization under repeated runs.

## OneDrive fake completion timeout

- Test: tests/test_onedrive.py::test_token_file_mode_0600.
- Observed failure: waiting for stored account completion exceeds the five-second wait_for limit (tests/conftest.py:276).
- The S-12 plan explicitly excludes fixing this pre-existing flake. Future work should isolate fake sign-in completion timing and verify synchronization; do not merely increase a timeout without evidence.
- Do not inspect or print real provider credentials or stored tokens when investigating.
