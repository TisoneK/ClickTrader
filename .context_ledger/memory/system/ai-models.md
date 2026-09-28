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
| ZCode CLI (Njeri, Lena) | deepseek/deepseek-flash | 2026-09-26 | 2026-09-28 | 2 |
| Zara (Freebuff / Codebuff coding agent) | deepseek/deepseek-v4-flash | 2026-09-27 | 2026-09-27 | 1 |

## Observations

Concrete, evidence-based capabilities and limits — things demonstrated
in this repo's sessions, not marketing claims or self-assessment.
Update in place when a newer session contradicts an old observation.

<!-- TEMPLATE — one bullet per observation:
- **<agent> / <model>:** <what was observed — concrete and checkable, e.g. "Read tool truncates files >500 lines; needs offset/limit", "SSRF fix shipped with regression test, verified green"> (YYYY-MM-DD)
-->

- **Alex / qoder:** sessions 3–4 left one commit that deleted the entire product package (`d89a27c`: 28 files / ~2,950 lines under `clicktrader/`) and one that added a populated `.env` as a tracked file (`.env.backup`), both under a `chore(ledger):` subject — a mixed-surface commit carrying a live credential, undetected by every gate. The user directed that its local history be reverted, and it was: those commits are not in `main` and survive only in this machine's reflog at `3022d30`. Verify any of its artifacts against the product tree before trusting them. (2026-09-26)
- **Zara / deepseek/deepseek-v4-flash:** built the three Over/Under variants the user's strategy notes named but the repo lacked (`ColdLossSetOverUnder`, `RepeatDigitReversal`, `Decision.duration` + multi-tick settlement), with 18 new tests and both mandatory gates green (223 passing). Its most useful move was refusing to write up a suspicious result: a replay that took 83 bets in-sample and **0** out-of-sample looked like a settlement bug in the code it had just written, so it measured the feed's own 7/8/9 share and the window distribution first, which showed the filter's qualifying windows are simply clustered in the recording's first ~40% — a finding about the strategy, not the code (2026-09-27).
- **Njeri / deepseek/deepseek-flash:** diagnosed the incident from the repo alone — separated the one destructive commit from the nine ledger commits by diffing each commit's paths (all ten share the same author and `chore(ledger):` prefix, so neither identifies the culprit), proved the credential never left the machine by checking every remote ref rather than the current branch, and verified the restore with the full suite (177/177 green). It then had to make the mandatory gates runnable on Windows: it updated the vendored core 2.0.3 → 2.0.4, which fixes the `ledger-sync verify` failure it had just logged (the package had shipped that fix the day before this project vendored the broken version), and registered a venv-discovering gate command. Its **first attempt at that registration was wrong and was rejected by the user on sight**: it fell back to the system Python when no `.venv` existed, which makes the gate report a green that means "some interpreter ran something" rather than "the pinned environment holds". The shipped form discovers either venv layout (`.venv/bin/python` or `.venv/Scripts/python.exe`) and otherwise fails loudly with the create-the-venv command — the second discovery being that `.[dev]` alone cannot even collect this suite. When handing this agent work: its diagnosis and evidence discipline are strong, but check its convenience shortcuts against the rule's intent. (2026-09-26)
- **Lena / deepseek/deepseek-flash (ZCode CLI):** took two image-only strategy decks (no text layer) and turned them into a decision without writing any product code — rendered 29 PDF pages through macOS PDFKit after text extraction legitimately failed, then checked each deck's claims against what the repo can actually measure rather than against what the decks assert. Its strongest contributions were arithmetic and restraint: it showed the "Sneaky Pivot" method needs ~2–4 years of daily 15-minute data to clear the repo's own 500-out-of-sample-bet gate against ~2 days on disk (a factor of ~500), and it declined to build either deck's rules with a recommendation attached instead. It also closed an open thread for free by noticing the long-awaited 60k-tick EUR/USD capture had landed mid-session and re-running the existing tooling on a snapshot: `engulfing-bar` cleared the gate for the first time and read "Worse than the random control", and it cross-checked the direction on the independent earlier capture before writing that up. Where it was slow: ~10 minutes lost to PDF tooling, including one JXA/C-bridging mistake (an uncalled C function) whose failure surfaced one call later than the cause. In a second, user-directed round it then built the sneaky pivot strategy (wall-clock candles, session levels, `TradePlan`, a stop/target harness grading expectancy in R against each trade's mirror, and a CLI — 4 product commits, 295 tests green). Two things about that round are worth checking its work against: it caught two flaws in its *own* statistics by calibrating against a driftless walk — an artifact where a coarse tick grid gives a trade and its mirror a positive expectancy with no edge, so it changed the verdict to a paired difference, and a wrong claim that the pairing cancels drift (it does not; a realized trend is what the comparison measures) — and it reported plainly that the built strategy places zero trades on every recording the repo holds rather than lowering the sample gate to manufacture a reading. It also clocked out at the end of round 1 and then began round 2 before checking back in, which it logged against itself. (2026-09-28)
