"""Forex, on the same account as the digit contracts (Deriv) but a genuinely different game.

Digit contracts have a *provable* -5% expected value (DESIGN.md: the payout formula's `p` cancels out
algebraically). Forex direction has no such proof either way — whether any strategy has an edge is a
real empirical question, not something algebra can settle before a line of code runs. This package tests
that question directly, at the safer end of what Deriv offers on this side (fixed-stake Rise/Fall options
on a forex underlying, chosen deliberately over real leveraged CFD margin trading — see chat/commit
history for why), reusing the shared, instrument-agnostic pieces of the digit-contract work
(`clicktrader.recording`, `clicktrader.ledger`, `clicktrader.limits`, the generic half of
`clicktrader.stats`, `clicktrader.strategies.History`) rather than duplicating them.

What does *not* carry over from the digit-contract side, and why this is its own package rather than an
extension of `clicktrader.model`/`clicktrader.harness`:

- `clicktrader.model.Contract` assumes a fixed win probability and settlement exactly one tick later.
  Neither holds for forex: direction accuracy is unknown until measured, and a position here is evaluated
  over a chosen horizon (many ticks), not the next one.
- `clicktrader.harness.replay` settles every decision against `ticks[i+1]`. A horizon-based settlement
  needs its own loop — `forex/harness.py` provides it.

The natural null hypothesis a control strategy tests here is that short-horizon direction is close to a
coin flip — the forex analogue of digit uniformity being the null on the other side. It is an empirical
claim about market efficiency, not a proof, and is treated as exactly that: a thing to check, not assume.
"""
