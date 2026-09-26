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
- **Problem:** this repo's declared dev environment cannot run this repo's own
  test suite. `pyproject.toml` puts pytest in `[dev]` and declares the runtime
  deps as separate extras (`[deriv]` = websocket-client, `[browser]` =
  playwright), but `tests/test_cli.py`, `test_deriv_api.py`,
  `test_deriv_trading.py` and `test_executor.py` `import websocket` at module
  top level and `test_browser_driver.py` imports `playwright`, none of them
  guarded. A venv built exactly as `system/environments.md` documented
  (`uv pip install -e '.[dev]'`) therefore fails collection in 5 files: the
  documented recipe and the suite disagree, and the gate goes red for a reason
  that has nothing to do with the code.
- **Cost:** two extra install rounds and a misleading red gate; the missing
  extras surface only by reading collection errors. Masked in the other
  direction too — this machine's system Python happens to carry
  websocket-client and playwright in its user-site, so `python -m pytest -q`
  there passed 177 while the pinned venv could not collect. A gate that is
  green on one interpreter and red on another, for install reasons, is exactly
  the muddle a gate exists to prevent.
- **Cause:** the package guards its own optional imports (it raises "the
  'deriv' extra is required: pip install -e '.[deriv]'"), but the tests import
  the third-party modules directly, so that guard never runs.
- **Workaround / fix:** install the full set — `uv pip install -e
  '.[dev,deriv,browser]'` in the venv; both environment recipes now say so.
  Deliberately NOT fixed by adding `pytest.importorskip` to those test modules:
  that converts a missing dependency into a skipped module and a green gate,
  which is the same false green the venv rule exists to reject. The real fix is
  the user's call — declare the suite's needs in one extra, or add the skips
  *and* accept that green then means "tested what happened to be installed".
- **Prevent next time:** keep the documented install recipe and the suite's
  actual top-level imports in sync; `.[dev]` plus unguarded third-party imports
  is a trap that fires on every fresh machine.

---
## 2026-09-26 — Njeri / deepseek-flash
- **Problem:** `playwright` could not be installed on this link. Three attempts —
  `uv pip install -e '.[browser]'` (network timeout at uv's default 30 s), the
  same with `UV_HTTP_TIMEOUT=900` (an extraction I/O failure, then a stall), and
  `python -m pip download playwright` (38.6 MB wheel, ~50 KB/s, cut mid-file,
  killed after ~25 minutes) — none completed, so `tests/test_browser_driver.py`
  still cannot collect and the gates stay red by those 6 tests.
- **Cost:** ~25 minutes of retries across two tools plus a stalled background job
  that had to be killed.
- **Cause:** link speed, not tooling — measured ~1 MB per 20 s against a 38.6 MB
  wheel. Worth knowing: uv reports a slow download as `Failed to extract archive
  ... I/O operation failed during extraction`, which reads like a corrupt wheel
  and sends you chasing the wrong problem.
- **Workaround / fix:** handed the user one command to run manually —
  `uv pip install playwright --python .venv/Scripts/python.exe` (uv venvs ship no
  `pip`). No browser binaries needed: the module drives a `FakePage`, so the PyPI
  package alone unblocks the remaining 6 tests and both gates.
- **Prevent next time:** on a slow link, sample the download rate before retrying
  a large wheel three ways, and hand the command over instead of burning the
  session on it.
