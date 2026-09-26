# Agent + Model Registry (update in place)

Which agents and models have worked on this repo — and what they've
shown they can and can't do here. Update your row each session (last
seen + session count); add a row only if this **(agent, model) pair** is
new. The Observations section is how the user learns which agent to hand
which task, and how agents learn a predecessor's blind spots (and verify
its work accordingly).

> **Update in place — do NOT append a duplicate.** This is not an
> append-only log. There is exactly one row per (agent, model) pair: to
> correct a count, model note, or date, **edit that row** — its prior value
> is safe in git history, so you lose nothing. Never add a second row for a
> pair that already exists (that is how a registry ends up with two rows
> and conflicting counts). Different models for the same agent are separate
> rows — that is expected, not a duplicate. `sh .context_ledger/core/bin/ledger-mem
> check` (Windows: the `.ps1`) flags a duplicated (agent, model) key.

<!-- TEMPLATE — one row per agent+model pair:
| <agent name> | <model id> | YYYY-MM-DD | YYYY-MM-DD | <count> |
-->

| Agent | Model | First seen | Last seen | Sessions |
|---|---|---|---|---|
| Wanjiru (Claude Code, desktop app) | claude-opus-5-5 | 2026-09-24 | 2026-09-24 | 1 |
| Alex (reported model string `qoder`) | qoder | 2026-09-26 | 2026-09-26 | 2 |
| Njeri (ZCode CLI) | deepseek/deepseek-flash | 2026-09-26 | 2026-09-26 | 1 |

## Observations

Concrete, evidence-based capabilities and limits — things demonstrated
in this repo's sessions, not marketing claims or self-assessment.
Update in place when a newer session contradicts an old observation.

<!-- TEMPLATE — one bullet per observation:
- **<agent> / <model>:** <what was observed — concrete and checkable, e.g. "Read tool truncates files >500 lines; needs offset/limit", "SSRF fix shipped with regression test, verified green"> (YYYY-MM-DD)
-->

- **Alex / qoder:** sessions 3–4 left one commit that deleted the entire product package (`d89a27c`: 28 files / ~2,950 lines under `clicktrader/`) and one that added a populated `.env` as a tracked file (`.env.backup`), both under a `chore(ledger):` subject — a mixed-surface commit carrying a live credential, undetected by every gate. The user directed that its local history be reverted, and it was: those commits are not in `main` and survive only in this machine's reflog at `3022d30`. Verify any of its artifacts against the product tree before trusting them. (2026-09-26)
- **Njeri / deepseek/deepseek-flash:** diagnosed the incident from the repo alone — separated the one destructive commit from the nine ledger commits by diffing each commit's paths (all ten share the same author and `chore(ledger):` prefix, so neither identifies the culprit), proved the credential never left the machine by checking every remote ref rather than the current branch, and verified the restore with the full suite (177/177 green). On this Windows box the mandatory `pre-commit` gate cannot pass as configured (no `.venv/`), so it ran the equivalent command by hand and logged the gate failure instead of reporting a false red. (2026-09-26)
