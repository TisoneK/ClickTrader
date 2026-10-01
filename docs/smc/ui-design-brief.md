# ClickTrader live view - design brief (owner, 1 Oct 2026) and where the page stands

**Intent.** An instrument you glance at, not a report that explains itself. Within two seconds: is the feed healthy, can
it trade, where is price, is a position open. Moving away from: gradient background and logo, pastel tinted pills, identical
shadowed cards, a gray uppercase label on every card, captions under everything, a four-tile stat grid, red used for "waiting".

| # | Requirement | State in `clicktrader/ui/page.html` |
|---|---|---|
| 1-2 | Chart and open position visible on a 13-inch laptop without scrolling; order: status strip, chart, trades, rest | Done; checked at 1280x720 (no page scroll) |
| 3 | Plan once, on the chart, with a one-line summary; no duplicate card or ladder | Done: summary line above the chart; ladder and four-tile grid removed |
| 4 | Trades compact, open position pinned first, demo separated from paper | Done: open position block, then demo table, then paper table (labelled "not evidence") |
| 5 | Evidence counter tied to demo trades only, in the status strip | Done |
| 6-10 | No gradients; flat surfaces; hairline borders, no shadows; one accent; red/green only for direction and P&L; gradients only where they encode data | Done: none used. Zone/level fills are flat translucent areas (data) |
| 11 | Large tabular numerals for price and account; quiet labels | Done |
| 12 | Deliberate flat logo | Done: wordmark plus one flat square in the accent colour |
| 13-15 | Light, dark, follow-system, remembered; dark default; chart colours designed per theme | Done: System/Light/Dark control, stored in the browser, dark when nothing stored; separate chart tokens per theme |
| 16-17 | One status strip; four-state vocabulary | Live (cyan, circle), Stale (amber, diamond), Disconnected (violet, triangle) as feed health; Watch-only as the mode badge beside it. Shape differs as well as colour |
| 18 | No live-looking plan over a stale or disconnected feed | Done: chart dims, plan replaced by the reason, veil text on the chart |
| 19 | Headline and trade log never disagree; an open trade can't read "waiting" | Done: the open position is fed by the run (`on_state`), shown in headline, side block and on the chart; a stale feed shows it as "last known" |
| 20 | No overlapping labels | Done for chart labels (first-free-slot placement; grid numbers skip prices that carry their own label). Checked by eye on three charts, not by an automated test |

Not covered by an automated test: the visual layout (checked in the in-app browser at 1280x720, 768 and 375 wide, dark and
light, with injected open-position, stale and disconnected states).
