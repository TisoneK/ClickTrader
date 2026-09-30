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
class Mark:
    """A point on a bar — a swing high (`above=True`) or swing low."""

    index: int
    price: float
    above: bool = True


class _Canvas:
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
    control: Sequence[str] | None = None,
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
    if control:
        for i, state in enumerate(control[:n]):
            colour = UP if state == "demand" else DOWN if state == "supply" else (190, 190, 190)
            canvas.rect(x_of(i) - int(step / 2), 8, x_of(i) + int(step / 2), 18, colour)
    with open(path, "wb") as handle:
        handle.write(canvas.png())
