# Session 9 notes — Lena (S009), 2026-09-28

Session-scoped detail for the review at
`office/reviews/2026-09-28-review.md`. Durable findings were promoted to
`tasks/parking-lot.md`, `tasks/backlog.md` and
`inefficiencies/log.md`; this file keeps the reading itself and the dead
ends, which are useful only if someone revisits the material.

## The source material

Two image-only PDF slide decks (no text layer, 1376×768, ~12 MB each),
read from the user's Desktop, never committed:

- `~/Desktop/The_Supply_and_Demand_Playbook.pdf` — 14 pages, "Gemini Notebook"
  watermark, deck title same as filename, subtitle "How to track and trade with
  institutional 'smart money'".
- `~/Desktop/Sneaky_Pivot_Blueprint.pdf` — 15 pages, same generator,
  presented as "The Sneaky Pivot Tactical Playbook — how to trade with one
  chart, zero indicators, and 15 minutes a day". The user attached this one
  twice in the same message; the two attachments were byte-identical in
  content (same 15 pages), so it is a duplicate upload, not a second document.

### Deck 1 — Supply & Demand Playbook, page by page (paraphrased)

1. Title / cover slide: a chart with supply and demand boxes, key levels, RSI,
   "smart money inflow", institutional activity "high".
2. Retail reality vs institutional reality: small capital "getting faked out"
   against "billions of dollars leaving undeniable chart footprints".
3. Small choppy candles = "retail noise, ignore completely"; 3+ large
   identical-coloured candles = "the footprint of smart money loading orders".
4. The three signatures of an origin zone: momentum (aggressive buying/selling),
   consolidation (accumulation before a breakout), wicks (limit orders absorbing
   pressure at a price floor).
5. Mechanics: (a) find the last opposite-coloured candle before the run-up,
   (b) box that candle's high and low exactly, (c) extend the box right into
   empty future space.
6. Three phases: blast-off, the wandering, return to origin. "Never chase the
   blast-off — wait for the re-test."
7. Expectation vs reality around a minor-support break: retail shorts the break
   and is stopped out; institutions use that liquidity to fill a demand block.
8. The trigger, as a binary: ABORT when small choppy candles bleed through the
   zone; EXECUTE when a long lower-wick doji is followed by a "massive" bullish
   engulfing candle inside the zone.
9. Trade architecture: entry at the engulfing candle's close; stop tucked below
   the absolute bottom of the zone; take-profit at the next major supply zone.
10. Dynamic zoning: when momentum destroys a zone, delete it, find the origin
    of the new momentum, draw the next zone there.
11. "The secret edge: confluence" — supply/demand box + Fibonacci retracement =
    "the high-conviction multiplier".
12. Fibonacci calibration: draw swing low to swing high; levels 38.2 / 50.0 /
    61.8 / 78.6; take-profit at the −27 extension.
13. "The ultimate overlap": when the 61.8% level sits inside the demand zone,
    enter there and risk 2% instead of 1%; take profit at the −27 extension.
14. Execution checklist (SPOT → DRAFT → WAIT → CONFIRM → STACK) and the closer
    "Stick to the blueprint. You are just one trade away."

### Deck 2 — Sneaky Pivot Blueprint, page by page (paraphrased)

1. Title slide; a quote attributed to "Doug, 26-year professional trader":
   "you don't need to get smarter, you need to get simpler".
2. The standard way (multiple monitors, 5+ indicators, stress) against the
   sneakier way (one screen, 15-minute timeframe, zero indicators, four
   horizontal lines, "emotionless execution").
3. Three parameters: the 15-minute rule (never change timeframe), four static
   lines drawn before the session, and a three-candle 45-minute entry engine.
4. Step 1, establishing the range: Range High = previous day's highest printed
   price, Range Low = previous day's lowest. Drawn by eye: "put a line on top,
   a line on the bottom".
5. Step 2, finding the swings: scroll left for the next highest price level
   above the Range High (Swing High) and the next lowest below the Range Low
   (Swing Low). Slide notes these are what "The Rumers Magic Lines" compute in
   TradingView.
6. Geography: above Range High → "the sell zone" ("only sell here"); between
   the two range lines → "the waiting room" ("twiddle your thumbs, do nothing");
   below Range Low → "the buy zone".
7. The morning ping-pong: the first 15 minutes chop between the range lines,
   then price usually picks a direction and visits a swing line. "We do not
   predict the direction."
8. The 45-minute engine: [0–15m] the anchor candle plows to the boundary;
   [15–30m] the "sneaky candle" tests the low's legitimacy and proves intent to
   buy back up, "prevents us from buying a sucker candle"; [30–45m] the trigger
   candle crosses the sneaky candle's high — "the cross".
9. Execution protocol: entry is the exact moment price crosses the high of the
   sneaky candle (example shown: "ENTRY 49,521"); rule of crossing — one candle
   must go over another.
10. "Market muscle memory and the Guardian Angel": stop-loss sits directly under
    the swing low, which was "tested for 30 consecutive minutes", used as a
    literal physical protection device; the stated flaw of most traders is never
    having mapped the boundaries in the first place.
11. Adapting to reality: if the opening 15-minute candle consumes most of the
    daily range, collapse the lines to that candle's own high and low; if bottom
    wicks test an area three times and hold, that is the localized floor.
12. Worked examples, two US tickers: AOI (system worked, full run to Range High,
    +$3,000) and GGLL (looked flawless, stopped out). Takeaway: "an edge, not a
    crystal ball".
13. "Trusting the lower buyer": real charts are jagged; the trade may sit there
    and "suck to be in"; as long as price holds the Guardian Angel low the trade
    is "mathematically valid" — do not cut it out of boredom.
14. Target architecture: strictly range-bound, so the target is a return to the
    opposite side of the range; or scale out against the biggest seller block.
15. Daily cheat sheet: setup 08:30–09:30, the rules of engagement, and the
    45-minute execution (15m let the market pick a boundary → 30m wait for the
    sneaky candle to test it → 45m enter on the cross, stop below the buyer,
    target the opposite zone).

## Readings of what is and isn't specified

Recorded here because it is the analysis, not the conclusion (the conclusion is
in the review and in the parking-lot rows):

- Deck 2 is a near-complete mechanical spec — its four line definitions, the
  three-candle roles, the entry trigger, the stop and the target all have
  precise definitions. The genuinely under-specified parts are the "reduce to
  the opening candle's high/low" fallback and the "scale out against the biggest
  seller block" exit.
- Deck 1's under-specified parts are most of it: "3+ large candles" (size
  relative to what?), "the previous opposite-coloured candle" (which one when a
  run-up follows several?), "defense", "the biggest seller block". These are the
  researcher's degrees of freedom, and there is no way to fix them without
  choosing thresholds, which turns the deck into a different (someone else's)
  strategy.
- Both decks assume a session with a beginning and an end. That assumption is
  invisible in the decks themselves but it is the single biggest structural
  mismatch with this repo, which records a continuous 24h FX feed and
  broker-generated synthetics.

## Measurements taken (detail behind the review's table)

Snapshot: `cp recordings/forex/live-eurusd-20260928.jsonl /tmp/eurusd-0930.jsonl`
(60,315 lines at the moment of the copy; the live recorder kept appending
afterwards, so a re-run on the file itself will read a different, larger file
and slightly different numbers).

```
.venv/bin/python -m clicktrader forex-replay-all /tmp/eurusd-0930.jsonl \
    --strategies engulfing-bar pin-bar inside-bar
```

family-corrected to z=2.39 for three strategies; out-of-sample half only:

- `engulfing-bar` 597 bets, 0.385 (0.339–0.434) vs control 0.473 (0.425–0.522)
  → "Worse than the random control". In-sample 0.336 (worse than OOS, so not a
  tuning artefact). First time this strategy has cleared the 500-bet gate.
- `pin-bar` 477 bets, 0.413 (0.360–0.468) vs control 0.409 (0.357–0.464)
  → NO VERDICT (23 bets short); dead level with the control either way.
- `inside-bar` 177 bets, 0.424 (0.339–0.514) vs control 0.443 (0.360–0.529)
  → NO VERDICT; fires too rarely at `bar_size=10` to clear the gate on this
  instrument without a much longer capture.

Second sample, same command against `recordings/forex/live-eurusd.jsonl`
(2026-09-25): `engulfing-bar` 0.368 vs control 0.418 (418 bets → NO VERDICT),
`pin-bar` 0.356 vs control 0.355 (343 bets), `inside-bar` 0.395 vs control
0.417 (114 bets). Engulfing-bar is below its control in both captures
(−0.050 and −0.088); only the newer capture has the power to say it decisively.

## Dead ends and friction worth remembering

- The PDFs have **no text layer** (zero `/Font` objects, 28–30 `/Image` objects
  each), so text extraction was never going to work — rendering was the only
  route. `pdftotext` is not installed on this machine and `pypdf` is not in the
  venv, and I chose not to install anything for a read-only task; macOS PDFKit
  via `osascript -l JavaScript` did it with no network or new dependency.
  Logged to `office/inefficiencies/log.md` with the working recipe.
- JXA gotcha that cost a retry: C functions bridged into JavaScript must be
  *called* — `const cs = $.CGColorSpaceCreateDeviceRGB;` silently passes a
  function reference, `CGBitmapContextCreate` then returns null, and the
  failure surfaces one call later as `Invalid parameter not satisfying:
  cgImage != NULL`. The fix is `$.CGColorSpaceCreateDeviceRGB()`.
- First attempt at extracting text returned 14 empty pages rather than an
  error — a reminder that "the extractor returned nothing" and "there is
  nothing to extract" look identical until you check the file's internals for
  font objects.
