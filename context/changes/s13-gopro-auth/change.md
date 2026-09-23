---
change_id: s13-gopro-auth
title: GoPro without a hand-pasted token
status: implementing
created: 2026-09-20
updated: 2026-09-23
archived_at: null
---

## Notes

The blocking question here is external, not a codebase question and not a framing one: whether
GoPro publishes any sign-in a third-party application may use. `/10x-research` is codebase-only
("Always run fresh codebase research") and `/10x-frame` needs an observation to reframe, so this
change is the first user of a self-authored draft skill, `.claude/skills/rune-spike/SKILL.md`
(untracked; `.gitignore` ignores `.claude/skills/*/`), which answers one external question with
today's vendor documentation plus the smallest experiment. The claim it must confirm or refute is
`context/archive/2026-09-07-cloud-source-ui/research.md:259` — "no public OAuth" — with a dated
link, not from memory. After the draft proves itself here it is ported into `@piotr-miller/ai-toolkit`
(where it needs a `derived_from` exemption: `rune-spike` has no `10x-*` ancestor) and this copy is
deleted.
