"""Draw the chart the way a person sees it, with what the engine sees laid on top.

The method this package implements is identified *visually*, and until this module existed nothing the
engine found had ever been compared with a rendered chart — so whether the code sees what the eye sees was
an open question answered only by argument. This makes it a thing to look at: candles, then every object
the engine names (levels, bands, gaps, swing points, blocks) drawn in place, so a person can say "it found
that, it missed this" from the picture rather than from a log.

Pure standard library (a PNG is a zlib stream), so there is no dependency to install and no font: the
picture carries no text, only shapes. The legend is colour, and it is written out in `LEGEND` so it does not
have to be remembered.

Everything drawn is axis-aligned — wicks are vertical, levels horizontal, boxes rectangles — which is also
all the material itself ever draws.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass

from ..forex.candles import Candle

LEGEND = {
    "candle up": "teal body, teal wick",
    "candle down": "red body, red wick",
    "level / pool": "thin blue line (the level the engine holds)",
    "band": "translucent blue box, drawn at the level's width",
    "gap": "translucent yellow box (unfilled fair value gap)",
    "block": "translucent orange box (order block)",
    "swing high": "small white tick above the bar",
    "swing low": "small white tick below the bar",
    "control strip": "thin strip along the top: teal = demand in control, red = supply",
}

BACKGROUND = (250, 250, 247)
UP = (38, 150, 140)
DOWN = (205, 70, 70)
LEVEL = (40, 90, 200)
GAP = (235, 190, 40)
BLOCK = (240, 140, 40)
SWING = (20, 20, 20)
GRID = (232, 232, 228)


# A 5x7 bitmap font, so the engine can name what it sees in the picture ("HH", "CHOCH", "SWEEP") instead of
# leaving the reader to decode colours. Uppercase, digits and a few marks only; anything else draws as a blank.
_FONT_ROWS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    ":": ["00000", "00100", "00100", "00000", "00100", "00100", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    "/": ["00001", "00001", "00010", "00100", "01000", "10000", "10000"],
    "%": ["11001", "11010", "00010", "00100", "01000", "01011", "10011"],
    ">": ["10000", "01000", "00100", "00010", "00100", "01000", "10000"],
    "<": ["00001", "00010", "00100", "01000", "00100", "00010", "00001"],
    "=": ["00000", "00000", "11111", "00000", "11111", "00000", "00000"],
    "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
    ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
}
TEXT_H = 7


@dataclass(frozen=True)
class HLine:
    """A level: a price, drawn from bar `start` to bar `end` (inclusive; `end=None` runs off the right)."""

    price: float
    start: int = 0
    end: int | None = None
    color: tuple[int, int, int] = LEVEL


@dataclass(frozen=True)
class Box:
    """A zone: a price range over a span of bars, drawn translucent so the candles show through it."""

    low: float
    high: float
    start: int
    end: int | None = None
    color: tuple[int, int, int] = LEVEL
    alpha: float = 0.22


@dataclass(frozen=True)
class Label:
    """Text pinned to a bar and a price. `scale` multiplies the 5x7 glyphs; `anchor` is where the text sits
    relative to the point ("above", "below", "right")."""

    index: int
    price: float
    text: str
    color: tuple[int, int, int] = SWING
    scale: int = 2
    anchor: str = "above"


@dataclass(frozen=True)
class Segment:
    """A straight segment between two (bar, price) points — how structure lines and trade paths are drawn."""

    start: int
    start_price: float
    end: int
    end_price: float
    color: tuple[int, int, int] = SWING
    dashed: bool = False


@dataclass(frozen=True)
class Mark:
    """A point on a bar — a swing high (`above=True`) or swing low."""

    index: int
    price: float
    above: bool = True


class _Canvas:
    def text(self, x: int, y: int, text: str, color: tuple[int, int, int], scale: int = 2) -> None:
        """Draw `text` with its top-left at (x, y)."""
        for ch in text.upper():
            rows = _FONT_ROWS.get(ch)
            if rows:
                for ry, row in enumerate(rows):
                    for rx, bit in enumerate(row):
                        if bit == "1":
                            self.rect(x + rx * scale, y + ry * scale, x + rx * scale + scale - 1, y + ry * scale + scale - 1, color)
            x += 6 * scale

    def line(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], dashed: bool = False) -> None:
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for k in range(steps + 1):
            if dashed and (k // 6) % 2:
                continue
            x = x0 + (x1 - x0) * k // steps
            y = y0 + (y1 - y0) * k // steps
            self.rect(x, y, x + 1, y + 1, color)

    def __init__(self, width: int, height: int, fill: tuple[int, int, int]) -> None:
        self.w, self.h = width, height
        self.px = bytearray(bytes(fill) * (width * height))

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
        x0, x1 = max(0, min(x0, x1)), min(self.w - 1, max(x0, x1))
        y0, y1 = max(0, min(y0, y1)), min(self.h - 1, max(y0, y1))
        if x0 > x1 or y0 > y1:
            return
        inv = 1.0 - alpha
        for y in range(y0, y1 + 1):
            row = y * self.w * 3
            for x in range(x0, x1 + 1):
                i = row + x * 3
                if alpha >= 1.0:
                    self.px[i : i + 3] = bytes(color)
                else:
                    self.px[i] = int(self.px[i] * inv + color[0] * alpha)
                    self.px[i + 1] = int(self.px[i + 1] * inv + color[1] * alpha)
                    self.px[i + 2] = int(self.px[i + 2] * inv + color[2] * alpha)

    def png(self) -> bytes:
        raw = b"".join(b"\x00" + bytes(self.px[y * self.w * 3 : (y + 1) * self.w * 3]) for y in range(self.h))

        def chunk(tag: bytes, data: bytes) -> bytes:
            body = tag + data
            return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

        header = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def render_chart(
    candles: Sequence[Candle],
    path: str,
    *,
    lines: Sequence[HLine] = (),
    boxes: Sequence[Box] = (),
    marks: Sequence[Mark] = (),
    labels: Sequence[Label] = (),
    segments: Sequence[Segment] = (),
    control: Sequence[str] | None = None,
    price_range: tuple[float, float] | None = None,
    width: int = 1600,
    height: int = 800,
) -> None:
    """Write `candles` and their overlays to `path` as a PNG.

    `control` is one word per bar ("demand" / "supply" / anything else for unknown) drawn as a strip along
    the top, so the moment the engine decided the market had changed character is visible against the bars.
    """
    if not candles:
        raise ValueError("nothing to draw")
    left, right, top, bottom = 10, 10, 30, 10
    plot_w, plot_h = width - left - right, height - top - bottom
    n = len(candles)
    lo = min(c.low for c in candles)
    hi = max(c.high for c in candles)
    if price_range is not None:
        lo, hi = price_range
    else:
        for line in lines:
            lo, hi = min(lo, line.price), max(hi, line.price)
        for box in boxes:
            lo, hi = min(lo, box.low), max(hi, box.high)
    span = (hi - lo) or 1.0
    lo -= span * 0.03
    hi += span * 0.03
    span = hi - lo
    step = plot_w / n
    body_w = max(1, int(step * 0.6))

    def x_of(i: float) -> int:
        return int(left + (i + 0.5) * step)

    def y_of(price: float) -> int:
        return int(top + (hi - price) / span * plot_h)

    def x_end(end: int | None) -> int:
        return width - right if end is None else x_of(end)

    canvas = _Canvas(width, height, BACKGROUND)
    for k in range(1, 10):
        canvas.rect(left, top + plot_h * k // 10, width - right, top + plot_h * k // 10, GRID)
    for box in boxes:
        if box.high < lo or box.low > hi:
            continue
        canvas.rect(x_of(box.start), y_of(box.high), x_end(box.end), y_of(box.low), box.color, box.alpha)
    for i, c in enumerate(candles):
        colour = UP if c.close >= c.open else DOWN
        x = x_of(i)
        canvas.rect(x, y_of(c.high), x, y_of(c.low), colour)
        top_y, bottom_y = sorted((y_of(c.open), y_of(c.close)))
        canvas.rect(x - body_w // 2, top_y, x + body_w // 2, max(bottom_y, top_y + 1), colour)
    for line in lines:
        y = y_of(line.price)
        canvas.rect(x_of(line.start), y, x_end(line.end), y + 1, line.color)
    for mark in marks:
        x, y = x_of(mark.index), y_of(mark.price)
        if mark.above:
            canvas.rect(x - 2, y - 9, x + 2, y - 5, SWING)
        else:
            canvas.rect(x - 2, y + 5, x + 2, y + 9, SWING)
    for seg in segments:
        canvas.line(x_of(seg.start), y_of(seg.start_price), x_of(seg.end), y_of(seg.end_price), seg.color, seg.dashed)
    placed: list[tuple[int, int, int, int]] = []
    for lab in labels:
        w, h = len(lab.text) * 6 * lab.scale, TEXT_H * lab.scale
        x, y = x_of(lab.index), y_of(lab.price)
        if lab.anchor == "above":
            tx, ty, dy = x - w // 2, y - h - 12, -(h + 3)
        elif lab.anchor == "below":
            tx, ty, dy = x - w // 2, y + 12, h + 3
        else:
            tx, ty, dy = x + 6, y - h // 2, h + 3
        # never print one label over another: step away (up for "above", down otherwise) until the spot is free
        for _ in range(10):
            if not any(tx < px + pw and tx + w > px and ty < py + ph and ty + h > py for px, py, pw, ph in placed):
                break
            ty += dy
        placed.append((tx, ty, w, h))
        canvas.text(tx, ty, lab.text, lab.color, lab.scale)
    if control:
        for i, state in enumerate(control[:n]):
            colour = UP if state == "demand" else DOWN if state == "supply" else (190, 190, 190)
            canvas.rect(x_of(i) - int(step / 2), 8, x_of(i) + int(step / 2), 18, colour)
    with open(path, "wb") as handle:
        handle.write(canvas.png())
