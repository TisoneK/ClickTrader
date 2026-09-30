# Pillar 2 — the engine (market physics)

## Market control is a two-state machine

Control is either with **demand** or with **supply**, and it does not blend. The deck draws it as an
endless figure-eight: demand in control → change of character (demand fails) → supply takes control →
change of character (supply fails) → back. Price swings between *unmitigated* zones, and when one breaks,
control transfers.

## Change of character (CHOCH)

A **CHOCH** is the transition between those states. In the worked example: price is in a demand zone, puts
in a weak bounce, then breaks below the zone — and the system's status changes from "demand in control" to
"supply takes control", with the action being that a *new valid supply zone is established above* and
momentum now favours sellers.

So a CHOCH is not merely a break — it is a break that moves control, and the first thing it does is tell
you which side's zones to look for next.

## The traps — and why the left side of the chart decides

Three things look the same at the moment of the break, and the material is emphatic that two of them are
not reversals:

| what it is | what is to the left | what institutions are doing | what price does |
|---|---|---|---|
| **True reversal (CHOCH)** | a high-quality zone broken, clean structure behind it | shifting control permanently | permanent trend change |
| **Liquidity sweep** | consolidation or an imperfect trend, with obvious swing lows / stop-losses | hunting liquidity to fuel the *original* direction | **wick below the level, then rapid recovery** |
| **FVG mitigation** | an unfilled imbalance from earlier | rebalancing historical price delivery | **touches the gap, then immediately resumes the trend** |

Two explicit checks fall out of that table, both stated as rules rather than hints:

- **Before confirming a CHOCH, scan the left of the chart for unmitigated gaps.** A drop that is really
  price filling an old imbalance is a rebalancing event, not a reversal — and an "apparent CHOCH" that is
  one is marked wrong.
- **A break below a swing low that sits inside a known liquidity area is usually a trap**, not a CHOCH.
  Smart money targets those stop pools deliberately.

**Code status:** the code has **no notion of control at all**. It re-derives zones on every bar with no
directional state, and it treats *any* close beyond a level as a breakout. So every liquidity sweep in the
data has been counted as a breakout signal, and every gap-filling pullback likewise — the two traps the
material specifically warns about are, in the current implementation, indistinguishable from the setup.
This is the largest single difference between the code and the method, and it lives exactly where signal
identification lives.
