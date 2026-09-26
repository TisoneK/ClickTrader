# Inefficiencies Archive (cold storage — resolved entries, moved verbatim)

Entries leave `log.md` once they are explicitly marked RESOLVED / superseded /
fixed. They are cut here unchanged so a startup read of the live log stays
short, while the record of what was slow — and what fixed it — survives.

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
- **Status:** RESOLVED the same session, by registering a command that
  *discovers* the venv per platform instead of naming one literal path:
  `if [ -x .venv/bin/python ]; then .venv/bin/python -m pytest -q; elif [ -x
  .venv/Scripts/python.exe ]; then .venv/Scripts/python.exe -m pytest -q; else
  <loud message>; exit 1; fi` — and by creating the missing venv on this
  machine (`uv venv --python 3.12 .venv`, then the extras below) so the gate
  has a pinned interpreter to run. Two corrections to the original entry, both
  from the user, are worth more than the fix itself: (1) the "fall back to
  auto-discovery" suggestion above is **wrong** and was deliberately not
  shipped — a gate that silently tests against whatever interpreter happens to
  be on PATH reports green for an environment nobody pinned (the first draft of
  this registration did exactly that with system Python 3.14 + user-site
  pytest and was rejected on sight); the shipped form fails loudly and tells
  the agent to create the venv. (2) A single POSIX `if/elif` line cannot run
  under the `.cmd`/PowerShell launcher, so Windows sessions must invoke the
  `sh` helper from Git Bash — recorded in `system/environments.md` rather than
  left implicit.
