# Environments (update in place)

Machines and sandboxes agents have run on, and what it takes to work on
this project from each. One block per environment; update the matching
block (and its "last verified" date) every time you run on it again.

## Rules

1. **Match before you add.** At session start, check whether the machine
   you're on already has a block (use its "Identify by" line). Update the
   match; add a new block only for a genuinely new environment.
2. **Record what you verified, not what you assume.** A command belongs
   under "Verified commands" only after it ran successfully on this
   environment, this project.
3. **Agents never delete blocks.** An environment the project no longer
   uses may be pruned by the user; if you can't verify a block, leave it
   alone — its last-verified date already says how stale it is.
4. **Machine facts only.** Secret values go in `secrets/`; user
   preferences in `user/`; project-wide decisions in `plans/`.

<!-- TEMPLATE — one block per environment:
---
## <stable label — hostname, "Z sandbox", "GitHub Actions ubuntu-24.04"> (last verified YYYY-MM-DD)
- **Identify by:** <how an agent recognizes this env — hostname, $USER, workspace path>
- **OS:** <e.g., macOS 15.5 / Ubuntu 24.04 sandbox>
- **Runtimes:** <node X, python Y, ...>
- **Package manager:** <npm/bun/pnpm/pip/...>
- **Verified commands:** <install / test / lint / typecheck / dev-server commands that actually worked here, with cwd if it matters>
- **Quirks:** <e.g., "no psql installed", "port 3000 usually taken", "system Python locked down">
-->

---
## bao's Mac (last verified 2026-09-24)
- **Identify by:** macOS (darwin 24.6.0, x86_64), checkout at `/Users/bao/Code/ClickTrader`
- **OS:** macOS; bash
- **Runtimes:** system `python3` is 3.9.6 — too old (`requires-python >=3.11`) and there is no bare `python`; uv at `~/.local/bin/uv` with CPython 3.10–3.13 managed. Repo venv: `uv venv --python 3.12 .venv && uv pip install -e '.[dev]' --python .venv/bin/python`
- **Verified commands:** `.venv/bin/python -m pytest -q` (45 passed) · `.venv/bin/clicktrader simulate|check|replay`
- **Quirks:** `ledger-gates` auto-discovers `python -m pytest`, which fails here (no `python`) — explicit gates are registered in `workflows/gates.conf`. `git push` from an agent session in the Claude desktop app was blocked by its auto-mode classifier (2026-09-24). The context-ledger package clone lives at `~/Code/context` (not `~/Code/context-ledger` as the package QUICKSTART says).
