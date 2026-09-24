# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
its roster row (if left behind) says who was here; check the session
entry and backlog before starting.

<!-- TEMPLATE — replace everything below this comment:
- **Session:** YYYY-MM-DD — <agent> / <model>
- **Task:** <what is being worked on right now>
- **Status:** blocked (push not permitted from this session; target platform unknown — P-2026-09-24-1) | done | blocked (<blocker>)
-->

- **Session:** 2026-09-24 — Amara / claude-sonnet-5
- **Task:** `record-live` is running against the real site (user logged in by hand; login persists via the Playwright profile at `~/.clicktrader/browser-profile` — cookies only, no credentials stored anywhere, and none will be: user asked, declined per policy). Writing to `recordings/live-cryptonichub.jsonl`. Two real bugs found and fixed running it live (174d5bd): a login-detection race, and a `.textContent`-vs-`.innerText` parsing bug.
- **Status:** blocked (waiting) — the CLI process's own `--ticks 30000` stop point was overestimated (arithmetic error, corrected below); no need to restart it, just read the partial file once it's far enough. Math: MIN_BETS_REPORT=500 is out-of-sample bets only; `low-digit-over` fires on ~20% of ticks (confirmed live: 19.6%, 325/1661 so far); out-of-sample is 50% of the recording by default split → need ~5,000 total ticks for a bare verdict, ~8,000 for a comfortable margin. NOT 30,000. Next step once the file passes ~8,000 lines: `clicktrader replay recordings/live-cryptonichub.jsonl --strategy low-digit-over`, plus `clicktrader check` for the uniformity/independence tests. The running process can be left going past 8,000 for a tighter interval, or stopped (Ctrl+C / SIGTERM) once that read looks solid — either is fine, it's the user's call.
