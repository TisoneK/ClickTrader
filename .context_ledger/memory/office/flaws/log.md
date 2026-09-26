# Flaws Log (append-only — flows to the protocol package)

Friction caused by the `.context_ledger/` system or the protocol itself. See
`README.md` in this directory for the split between `flaws/` and
`inefficiencies/`.

Append-only, but compactable — the log never grows without bound:

- **Resolved entries move verbatim** to cold storage: once an entry is
  explicitly marked `RESOLVED` / `superseded` / fixed, cut it unchanged
  into `archive.md` in this directory so startup reads only the live
  entries. Age alone never makes an entry eligible — an unresolved flaw
  stays here as a live trap.
- **Repeats roll up:** when 3+ entries describe the same recurring
  protocol trap, append ONE consolidated `Recurring` entry — the pattern,
  how many times, the current workaround — and move the individual
  entries verbatim into `archive.md`. The live log keeps the pattern, not
  the repeats.

`ledger-mem prune` reports log sizes, archive-eligible entries (`--list`
names them), and roll-up candidates.

<!-- TEMPLATE — copy below the last entry:
---
## YYYY-MM-DD — <agent> / <model> (Session N)

- **Flaw:** <what in the protocol or .context_ledger/ system didn't work>
- **Symptom:** <what happened to the agent — the observable friction>
- **Root cause:** <why the protocol/.context_ledger/ let this happen>
- **Suggested fix:** <concrete change to the package — a step, a pitfall,
  a template, a rule>
- **Status:** open | fixed in package <commit-sha or date>
-->

---
## 2026-09-26 — Njeri / deepseek-flash (Session 5)

- **Flaw:** Nothing in the protocol's own machinery stopped a session from
  (a) deleting the entire product source tree and (b) committing a secret
  file, both inside commits prefixed `chore(ledger):`. Two sessions
  ("Alex", sessions 3–4) produced them locally, and the rule they broke —
  "two surfaces, never one commit" and "no secret values in any tracked
  file" — was only caught by the user reading `git status`, days later.
- **Symptom:** A `chore(ledger):` commit (`d89a27c`) removed 28 files /
  ~2,950 lines under `clicktrader/` and added `.env.backup` (populated
  `DERIV_TOKEN`/`DERIV_ACCOUNT_ID`/`DERIV_APP_ID`) to the tracked tree.
  The damage was invisible to `ledger-mem check`, `ledger-gates`, and
  `ledger-state`: the roster, STATE.md and the digest all looked healthy,
  because all of them summarize memory files, not the product tree. The
  next `git pull` then deadlocked on a conflict (our side deleted
  `clicktrader/cli.py`, the remote had modified it), which is how a human
  finally saw it.
- **Root cause:** The protocol's guardrails are all *prose* rules the agent
  must self-apply at write time; none is a check that runs. `ledger-gates
  run pre-commit` validates the staged diff for whitespace and runs project
  tests — it never asks "does this `chore(ledger):` commit touch product
  paths?" nor "does this commit add a file that looks like a secret
  container?". The exit checklist likewise has no "scan your own commits"
  step. An agent that misjudges its task therefore ships the mistake with
  every gate green.
- **Suggested fix:** Add two cheap universal checks to `ledger-gates run
  pre-commit`: (1) fail (or loudly warn) when a commit whose staged paths
  are predominantly under `.context_ledger/` also *deletes* paths outside
  it — the mixed-surface case this rule was written for; (2) fail when a
  staged addition matches secret-container patterns (`.env*`, `*.pem`,
  `id_rsa*`, `secrets.*`, `*.key`) or when added lines contain
  `<NAME>_TOKEN=`/`_SECRET=`/`_API_KEY=` style assignments. Add the same
  sweep to the exit checklist as a mandatory step ("scan the session's own
  commits for secret containers and out-of-surface deletions"). The check
  is mechanical; today it depends on the weakest model in the office
  applying the rule correctly.
- **Status:** open

---
## 2026-09-26 — Njeri / deepseek-flash (Session 5)

- **Flaw:** A roster row left by a session that ended without clocking out
  stays on the board looking live, and nothing distinguishes "in the office
  right now" from "gone, row never removed".
- **Symptom:** `roster.md` carried Amara (S002) as `Working` — "about to
  commit+push" — while her commits (`39e702d`, `ea89932`) had in fact
  landed on `origin/main` and she had no entry in `agents/sessions.md`. The
  next session (this one) had to reconstruct whether a peer was live before
  acting, and could not from the board alone.
- **Root cause:** Clock-out depends on the same push that a blocked session
  never completes (the Mac environment block records pushes refused by the
  desktop app's permission classifier), so the row is exactly the artifact
  that survives a session that died at the last step. `ledger-mem check`
  catches the opposite direction only — "a session entry was logged while
  your row still claimed the office" — never a row with no session entry.
- **Suggested fix:** Have `ledger-mem check` warn when the roster carries a
  row whose agent has no `sessions.md` entry for that session number (or
  entries older than the row's own last-modified commit), and give the
  roster template a "last activity" hint so a peer can judge staleness
  without reading git history.
- **Status:** open
