"""The small amount of statistics the project needs, in the standard library.

Everything here refuses to answer on a sample too small to mean anything (``SampleTooSmall``) rather
than print a number that looks like a result — DESIGN.md, open question 4.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

MIN_TICKS_UNIFORMITY = 2000
"""Below this the digit test is refused. At 2000 ticks a single digit running at 12% instead of 10%
is caught only about half the time at the 5% level — smaller samples are close to blind to any bias
worth caring about. (Power checked by simulation; see tests/test_stats.py.)"""

MIN_BETS_REPORT = 500
"""Below this many settled contracts the harness will not report a verdict on a strategy."""


class SampleTooSmall(ValueError):
    def __init__(self, what: str, have: int, need: int) -> None:
        super().__init__(f"{what}: {have} is too small a sample to report on — need at least {need}")
        self.have = have
        self.need = need


def chi2_sf(x: float, df: int) -> float:
    """P(X >= x) for X ~ chi-square(df): the regularised upper incomplete gamma Q(df/2, x/2)."""
    if x <= 0:
        return 1.0
    a, z = df / 2, x / 2
    if z < a + 1:  # series for P, then complement
        term = total = 1 / a
        n = a
        while abs(term) > abs(total) * 1e-15:
            n += 1
            term *= z / n
            total += term
        return max(0.0, 1 - total * math.exp(-z + a * math.log(z) - math.lgamma(a)))
    # continued fraction for Q (modified Lentz)
    tiny = 1e-300
    b = z + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return min(1.0, h * math.exp(-z + a * math.log(z) - math.lgamma(a)))


@dataclass(frozen=True)
class ChiSquare:
    what: str
    n: int
    statistic: float
    df: int
    p_value: float
    counts: dict[int, int]

    def rejects(self, alpha: float = 0.01) -> bool:
        return self.p_value < alpha

    def summary(self, alpha: float = 0.01) -> str:
        verdict = (
            f"REJECTED at {alpha:g} — the feed does not look like what it claims"
            if self.rejects(alpha)
            else f"not rejected at {alpha:g} — consistent with what the platform claims"
        )
        return (
            f"{self.what}: n={self.n}, chi2={self.statistic:.2f}, df={self.df}, "
            f"p={self.p_value:.4f} — {verdict}"
        )


def digit_uniformity(digits: Sequence[int], *, minimum: int = MIN_TICKS_UNIFORMITY) -> ChiSquare:
    """Are the ten digits equally likely? Pearson chi-square against uniform, df = 9."""
    n = len(digits)
    if n < minimum:
        raise SampleTooSmall("digit uniformity", n, minimum)
    counts = Counter(digits)
    expected = n / 10
    statistic = sum((counts.get(d, 0) - expected) ** 2 / expected for d in range(10))
    return ChiSquare(
        "digit uniformity", n, statistic, 9, chi2_sf(statistic, 9), {d: counts.get(d, 0) for d in range(10)}
    )


def digit_independence(digits: Sequence[int], *, minimum: int = MIN_TICKS_UNIFORMITY) -> ChiSquare:
    """Does a digit say anything about the next one? Chi-square test of independence on the 10x10
    table of consecutive pairs, df = 81. This is the claim every "hot digit" strategy is betting on."""
    if len(digits) < minimum:
        raise SampleTooSmall("digit independence", len(digits), minimum)
    pairs = Counter(zip(digits, digits[1:]))
    n = len(digits) - 1
    rows = Counter(a for a, _ in zip(digits, digits[1:]))
    cols = Counter(b for _, b in zip(digits, digits[1:]))
    statistic = 0.0
    for a in range(10):
        for b in range(10):
            expected = rows[a] * cols[b] / n
            if expected > 0:
                statistic += (pairs.get((a, b), 0) - expected) ** 2 / expected
    used_rows = sum(1 for a in range(10) if rows[a])
    used_cols = sum(1 for b in range(10) if cols[b])
    df = max(1, (used_rows - 1) * (used_cols - 1))
    return ChiSquare("digit independence (lag 1)", n, statistic, df, chi2_sf(statistic, df), dict(rows))


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% (by default) Wilson score interval for a proportion — sane at small n and near 0 or 1."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bonferroni_z(num_comparisons: int, alpha: float = 0.05) -> float:
    """The two-sided z-score `wilson_interval`/`mean_interval` should use so that, across
    `num_comparisons` strategies tested together, the chance that ANY of them looks "significant" by
    pure chance stays near `alpha` overall — not `alpha` per strategy.

    Testing 8 strategies at the default 95% interval (z=1.96) each gives roughly a
    ``1 - 0.95**8 ≈ 34%`` chance at least one looks significant from noise alone, not the 5% each
    interval's own label implies. This widens the interval per strategy (Bonferroni: target alpha
    becomes ``alpha / num_comparisons``) so a batch verdict is exactly as hostile to a false positive
    as a single one is meant to be — this project's harness has already caught exactly this failure
    mode once, on a real batch of 8 (see chat/commit history, not yet in DESIGN.md).
    """
    if num_comparisons < 1:
        raise ValueError("num_comparisons must be at least 1")
    target = 1 - alpha / (2 * num_comparisons)
    lo, hi = 0.0, 15.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if _norm_cdf(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def mean_interval(values: Iterable[float], z: float = 1.96) -> tuple[float, float, float]:
    """(mean, low, high) — normal-approximation interval for a mean."""
    xs = list(values)
    n = len(xs)
    if n == 0:
        return (0.0, 0.0, 0.0)
    mean = sum(xs) / n
    if n == 1:
        return (mean, mean, mean)
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    half = z * math.sqrt(var / n)
    return (mean, mean - half, mean + half)
