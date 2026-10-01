"""The engine's wording, translated for someone who has never read the code.

The engine talks in its own vocabulary ("SWEEP", "structure", "the slower chart disagrees"). The page's main view must not:
each engine message becomes one plain sentence, and anything this module does not recognise is left out of the main view
(it stays available, raw, in the diagnostics drawer)."""

from __future__ import annotations

import re

REASON = {
    "slower_chart": "The bigger charts (5 and 15 minutes) point the other way, so I am staying out until they agree.",
    "trend": "The only zone nearby is against the current trend, so it is not worth taking.",
    "room": "There is no clear space for price to travel to the next level, so a trade here would not pay enough for the risk.",
    "better_zone": "A better zone sits elsewhere in the same move, so I am waiting for that one instead.",
    "knife": "Price came back into the zone too violently, so I skipped it rather than catch a falling knife.",
    "dead": "Price closed straight through the zone, so it no longer counts.",
    "none": "No fresh buyer or seller zone is close enough to price to plan a trade.",
}


def why_nothing(code: str) -> str:
    return REASON.get(code, REASON["none"])


def why_waiting(side: str, source: str) -> str:
    if source == "zone":
        who, mover = ("seller", "down") if side == "sell" else ("buyer", "up")
        return (f"A fresh {who} zone: {who}s pushed price hard {mover} from here before, and some of their orders may still be "
                f"waiting. If they are, price should turn {mover} again.")
    return "The trend just changed direction, and this is the spot where that move started."


def _cancel_reason(text: str) -> str:
    t = text.lower()
    for key, words in (("higher timeframe", "the bigger chart turned against it"), ("stale", "price never came back to it within the hour"),
                       ("knife", "price fell into it too violently"), ("dead zone", "price closed straight through the zone"),
                       ("closed through", "price closed straight through the zone"), ("against the trend", "the trend turned against it"),
                       ("weaker zone", "a better zone exists in the same move"), ("room", "there was no room to the next level")):
        if key in t:
            return words
    return "it no longer qualified"


_EVENT = {
    ("SWEEP", "false"): "Price poked past {lvl} and came straight back. Stops were grabbed, not a real move.",
    ("BOS", "continuation"): "Price broke through {lvl} and the trend carried on.",
    ("BOS", "true"): "Price broke through {lvl} and the trend carried on.",
    ("CHOCH", "true"): "The trend changed direction at {lvl}.",
    ("CHOCH", "false"): "Price tried to change direction at {lvl} but it did not hold.",
    ("GAP FILL", "false"): "Price filled a gap near {lvl}; that is rebalancing, not a reversal.",
}
_NOTE = re.compile(r"\s*\[last: (?P<note>.*)\]\s*$")
_ORDER_NOTE = re.compile(r"(?P<side>sell|buy) order at (?P<price>[\d.]+) withdrawn . (?P<why>.*)$")


def sentences(view: str, plans: list[dict] | None = None) -> list[str]:
    """Plain sentences for one engine message; empty when it is plumbing (warm-up, counts) that belongs in diagnostics."""
    if view.startswith("the live feed stopped"):
        return ["The live price feed stopped. Nothing on this page is current until it comes back."]
    if not view or view.startswith(("warmed with", "warming up", "nothing seen yet", "only ")):
        return []
    out: list[str] = []
    note = _NOTE.search(view)
    if note:
        view = view[: note.start()]
        m = _ORDER_NOTE.search(note.group("note"))
        if m:
            out.append(f"The {m['side']} order at {m['price']} was cancelled: {_cancel_reason(m['why'])}.")
    m = re.match(r"waiting to (buy|sell) when price (falls|rises) to ([\d.]+)-([\d.]+), [\d.]+ (?:above|below) now\. "
                 r"Wrong beyond ([\d.]+), target ([\d.]+), ([\d.]+) to 1", view)
    if m:
        side, verb, lo, hi, stop, target, rr = m.groups()
        out.insert(0, f"Now waiting to {side} if price {verb} to {lo} - {hi}. Wrong beyond {stop}; target {target}.")
        return out
    m = re.match(r"(up|down|range) structure; last event ([A-Z ]+?)\s+(true|false|continuation)\s+at ([\d.]+)", view)
    if m:
        _, kind, verdict, lvl = m.groups()
        text = _EVENT.get((kind.strip(), verdict))
        if text:
            level = float(lvl)
            # a poke is a loss if it went past a plan's stop: the same rule applied the same way, whatever the story about it
            crossed = [p for p in (plans or []) if (p["side"] == "sell" and level >= p["stop"]) or (p["side"] == "buy" and level <= p["stop"])]
            if kind.strip() == "SWEEP" and crossed:
                p = crossed[0]
                text = (f"Price touched {lvl}, past the {p['side']} plan's stop at {p['stop']:g}. Had that trade been open it would "
                        "have been stopped out, whatever happened next.")
            out.insert(0, text.format(lvl=lvl))
        return out
    m = re.match(r"passed on a setup . (.*?)(?:\. Passed on \d+ so far.*)?$", view)
    if m:
        out.insert(0, f"Saw a possible trade and skipped it: {_cancel_reason(m.group(1))}.")
        return out
    if view.startswith("dropped:"):
        out.insert(0, "The waiting order was dropped: price closed through the zone.")
    return out
