# Flaws Archive (cold storage — resolved entries, moved verbatim)

Entries leave `log.md` once they are explicitly marked RESOLVED / superseded /
fixed. They are cut here unchanged so a startup read of the live log stays
short, while the record of what was broken — and what fixed it — survives.

---
## 2026-09-26 — Njeri / deepseek-flash (Session 5)

- **Flaw:** `ledger-sync verify` cannot pass on Windows, and it fails in a
  way that tells the agent to destroy a healthy core. The port-parse step
  aborts before any hash integrity is reported, and its failure is printed
  with the same "core is corrupt → `ledger-sync rollback`" instruction used
  for genuine corruption.
- **Symptom:** On Tison's Windows 10 box, `sh .context_ledger/core/bin/ledger-sync
  verify` emits ~20 parse errors and ends with `ledger-sync: PORT PARSE
  FAILURE — a script in core/bin cannot be parsed` / `If this core just
  arrived from a release: ledger-sync rollback <previous-version>`. Two
  distinct defects show up: `ledger-mem.ps1` fails under Windows PowerShell
  5.1 (`The token '||' is not a valid statement separator in this version`),
  and `ledger-state.ps1` fails under **both** 5.1 and pwsh 7.6.6
  (`Variable reference is not valid. ':' was not followed by a valid
  variable name character` — a `"$var:…"` interpolation that needs
  `${var}`). A session following the kickoff's Phase 1 literally would roll
  back an intact core; the same failure also makes the mandatory `exit` gate
  report two failing checks instead of one.
- **Root cause:** (a) `core/bin/ledger-sync` probes the interpreter as
  `command -v powershell || command -v pwsh`, so the built-in 5.1 wins over
  an installed PowerShell 7 even though the ports are written for 7;
  (b) `ledger-state.ps1` carries an interpolation that no PowerShell version
  accepts, so no engine choice rescues it; (c) the parse step is
  unconditional and its verdict is indistinguishable from corruption.
- **Suggested fix:** three small changes — probe `pwsh` before `powershell`;
  fix the `$var:` interpolations in `ledger-state.ps1` (use `${var}`); and
  give the parse failure its own verdict (`PORT DEFECT — core hashes were NOT
  checked; run sha256sum -c MANIFEST.sha256`) instead of the rollback
  instruction, since rolling back reinstalls whichever core shipped the
  defect. `system/environments.md` records the working substitute on Windows:
  the POSIX helpers run fine under Git Bash, and `sha256sum -c MANIFEST.sha256`
  inside `core/` verifies integrity independently.
- **Status:** RESOLVED — the package fixed this itself in core **2.0.4**
  (2026-09-23, one day before this project vendored 2.0.3), and its changelog
  entry names this exact failure mode ("Windows sessions could not pass their
  exit gate at all"), including the `$Label:` interpolation, the non-ASCII
  hazard in 5.1, and the one-engine `parse_ports` probe. The fix line above is
  what shipped: 2.0.4 now parses ports under *every* engine on PATH and adds an
  engine-free encoding guard. This project consumed it by updating the vendored
  core 2.0.3 → 2.0.4 the same session (`chore(ledger): update core to 2.0.4`);
  `ledger-sync verify` now reports `ps1 parse: OK (powershell 5.1.26100.9444,
  pwsh 7.6.6)` and `core OK ... (2.0.4)`, exit 0. Two clauses of the original
  entry are superseded by that: the session *did* run `update` once the user
  directed the Windows gate registration, and 2.0.4 did already carry the fix.
  The pre-existing evidence stands: `sha256sum -c MANIFEST.sha256` in
  `.context_ledger/core` exited 0 with 70 OK / 0 FAILED under 2.0.3, so the
  rollback advice would have been wrong.
