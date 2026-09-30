# Pillar 1 — the components (raw materials)

## Supply and demand zones

A **demand zone** is where aggressive accumulation happened — buyers stepped in; a **supply zone** is
where aggressive distribution happened — sellers dominated. The framing is that these are *footprints of
large-scale entry*, so when price returns the expectation is a reaction "based on historical aggression".

## Order blocks — the refiner

A macro supply or demand zone is wide. An **order block** is the refinement: the *single candle*
responsible for the initial imbalance, taken out of that zone. The stated purpose is practical rather
than aesthetic — isolating one candle lets the stop sit tighter, which raises the reward-to-risk on the
same idea and (in the material's words) increases the probability of a reaction.

**This is what the code calls a zone**: one candle, drawn wick to wick. That reading is confirmed here
rather than inferred.

## Inefficiencies — fair value gaps

When price moves too fast, the gap it leaves behind is a **structural imbalance**. Concretely, and as the
deck draws it: the gap spans from **candle 1's high to candle 3's low**, with the middle candle being the
displacement that crossed it. The stated behaviour is that the gap acts as a magnet, drawing price back
later to rebalance.

**The code's `fair_value_gaps` matches this definition exactly** — the strict version, no wick overlap.

## The zone quality scorecard

Three checks, and all three are meant to pass before a zone counts:

1. **Inefficiency (imbalance).** Did price move so fast that it left unfilled orders — i.e. was a gap
   created?
2. **Break of structure.** Did the move shatter previous market structure limits?
3. **Pushed distance.** Did price travel a *significant distance* before returning?

The worked example marks the three as "gap created", "structure broken", "long distance achieved".

**Code status (S010):** all three are in `smc/analyst.py`: the gap and the structure break are implemented and used; pushed distance is **measured and reported but not gated**, because the material gives no number and a gate would be an invented constant.
