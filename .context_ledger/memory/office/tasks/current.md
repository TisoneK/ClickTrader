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
- **Task:** `record-live` is running against the real site (user logged in by hand), writing to `recordings/live-cryptonichub.jsonl`, target 30,000 ticks (~8h at ~1 tick/s) so `low-digit-over`'s out-of-sample bet count clears MIN_BETS_REPORT (500). Two real bugs found and fixed running it live (174d5bd): a login-detection race, and a `.textContent`-vs-`.innerText` parsing bug.
- **Status:** blocked (waiting) — recording in progress in the background; next step once it finishes (or the user stops it early) is `clicktrader replay recordings/live-cryptonichub.jsonl --strategy low-digit-over` and also a `clicktrader check` for the uniformity/independence tests
