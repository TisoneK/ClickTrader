# Inefficiency Log (append-only — real friction only)

Append a block **only when something actually slowed you down** — a clean
session appends nothing (its `agents/sessions.md` entry is the record;
"none this session" blocks are noise, not history). But when something
bit you, the block is mandatory and honest: friction you absorb silently
is friction the next agent hits blind.

Most inefficiencies are project-local (an environment quirk, a one-off
cost) and stay here. When one is actually **protocol-level** — the core
workflow itself made you slower and every project would hit it — mark it
`Upstream: candidate`. `ledger-sync harvest` collects those (and open
`flaws/`) into the package for an upstream fix. Unmarked entries are
never harvested.

Append-only, but compactable — the log never grows without bound:

- **Resolved entries move verbatim** to cold storage: once an entry is
  explicitly marked `RESOLVED` / `superseded` / fixed, cut it unchanged
  into `archive.md` in this directory so startup reads only the live
  entries. Age alone never makes an entry eligible.
- **Repeats roll up:** when 3+ entries describe the same recurring thing
  (same failing tool, same root cause), append ONE consolidated
  `Recurring` entry — the pattern, how many times, the current
  workaround — and move the individual entries verbatim into
  `archive.md`. The live log keeps the pattern, not the repeats.

`ledger-mem prune` reports log sizes, archive-eligible entries (`--list`
names them), and roll-up candidates.

<!-- TEMPLATE — copy below the last entry:
---
## YYYY-MM-DD — <agent> / <model>
- **Problem:** <what went wrong or was slower than it should be>
- **Cost:** <rough time/effort wasted>
- **Cause:** <root cause if known>
- **Workaround / fix:** <what worked, or "unresolved">
- **Prevent next time:** <protocol/context change that would have avoided it>
- **Upstream:** candidate  ← add this line ONLY for protocol-level friction
  worth a core fix; omit entirely for project-local friction.
-->

---
## 2026-09-26 — Njeri / deepseek-flash
- **Problem:** `workflows/gates.conf` registers its mandatory commands as
  `.venv/bin/python -m pytest -q` (a POSIX venv path, correct on the Mac
  that bootstrapped it). On Tison's Windows checkout there is no `.venv/`
  at all, so `ledger-gates run pre-commit` fails with
  `sh: line 1: .venv/bin/python: No such file or directory` /
  `ledger-gates: FAILED (127)` — a *mandatory* gate cannot pass on this
  machine regardless of the code's health.
- **Cost:** Manual substitution: run `python -m pytest -q` by hand (177
  passed) and record the gate failure in the session notes so the red gate
  isn't mistaken for red tests.
- **Cause:** `gates.conf` has one command per gate with no platform
  dimension, but the core itself is cross-platform (§"Reading, gates, and
  Windows" ships `.cmd`/`.ps1` ports for every tool). A path that is
  correct for a POSIX venv is wrong on Windows (`Scripts/python.exe`), and
  the Mac has no bare `python` at all (see `system/environments.md`), so no
  single literal command satisfies both machines sharing the file.
- **Workaround / fix:** unresolved in-place — deliberately not edited, because
  any literal path fixes one platform and breaks the other. Needs a checked-in
  wrapper (e.g. `scripts/test` + `scripts/test.cmd`) that `gates.conf` calls.
- **Prevent next time:** let `gates.conf` express a command per platform, or
  make `ledger-gates` fall back to auto-discovery when the configured command
  is missing from the filesystem (loud notice, not a silent skip) instead of
  failing the gate with 127.
- **Upstream:** candidate
