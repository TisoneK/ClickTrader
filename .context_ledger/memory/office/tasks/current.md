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
- **Task:** user re-prioritized: prove the strategy in layer 2 (replay) before any deposit or live recording. Added `low-digit-over` (Over(1) bet whenever the last digit is 0/1, $0.10 stake) to strategies.py; confirmed on synthetic data it converges to the -5% pricing, same as every other barrier (f305e5b)
- **Status:** in progress — need a real recording (not synthetic) to test the strategy against the actual site's feed; browser adapter (5a3411b) is built but not yet run live
