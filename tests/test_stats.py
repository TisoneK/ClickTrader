import pytest

from clicktrader.stats import (
    SampleTooSmall, bonferroni_z, chi2_sf, digit_independence, digit_uniformity, wilson_interval,
)
from clicktrader.synthetic import synthetic_ticks


@pytest.mark.parametrize("x,df,p", [(16.919, 9, 0.05), (21.666, 9, 0.01), (3.841, 1, 0.05), (103.01, 81, 0.05)])
def test_chi2_matches_tables(x, df, p):
    assert chi2_sf(x, df) == pytest.approx(p, abs=1e-4)


def digits(n, seed=0, weights=None):
    return [t.digit for t in synthetic_ticks(n, seed=seed, digit_weights=weights)]


def test_refuses_small_samples():
    with pytest.raises(SampleTooSmall):
        digit_uniformity(digits(1999))
    with pytest.raises(SampleTooSmall):
        digit_independence(digits(1999))


def test_uniform_feed_is_not_rejected_too_often():
    rejected = sum(digit_uniformity(digits(2000, seed=s)).p_value < 0.05 for s in range(200))
    assert rejected / 200 < 0.10  # nominal 5%


def test_minimum_sample_has_the_power_the_docstring_claims():
    # MIN_TICKS_UNIFORMITY says a 12% digit is caught "about half the time" at 2000 ticks.
    w = [12] + [88 / 9] * 9
    caught = sum(digit_uniformity(digits(2000, seed=s, weights=w)).p_value < 0.05 for s in range(200))
    assert 0.35 < caught / 200 < 0.65


def test_a_clear_bias_is_caught():
    result = digit_uniformity(digits(10_000, weights=[15] + [85 / 9] * 9))
    assert result.rejects(0.01)


def test_independence_catches_a_sticky_feed():
    import random
    rng = random.Random(0)
    seq = [rng.randrange(10)]
    for _ in range(5000):
        seq.append(seq[-1] if rng.random() < 0.2 else rng.randrange(10))
    assert digit_uniformity(seq).p_value > 0.001  # marginals still look uniform…
    assert digit_independence(seq).rejects(0.01)  # …but the pairs give it away


def test_wilson():
    lo, hi = wilson_interval(50, 100)
    assert lo < 0.5 < hi and hi - lo == pytest.approx(0.19, abs=0.01)
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_bonferroni_z_matches_the_ordinary_95_percent_interval_at_one_comparison():
    assert bonferroni_z(1) == pytest.approx(1.96, abs=0.001)


def test_bonferroni_z_widens_as_comparisons_grow():
    z1 = bonferroni_z(1)
    z8 = bonferroni_z(8)
    z100 = bonferroni_z(100)
    assert z1 < z8 < z100


def test_bonferroni_z_matches_a_known_table_value():
    # 8 comparisons, family-wise alpha=0.05 -> per-test alpha=0.00625 -> two-sided z ~= 2.734 (standard table)
    assert bonferroni_z(8) == pytest.approx(2.734, abs=0.005)


def test_bonferroni_z_actually_restores_the_intended_family_wise_rate():
    # simulate: with an UNCORRECTED z=1.96, running many independent, genuinely-no-edge strategies
    # should make "at least one looks significant" happen far more than 5% of the time; the corrected
    # z should bring that back down near 5%.
    import random

    from clicktrader.model import HOUSE_EDGE

    def any_false_positive(z: float, num_strategies: int, seed: int) -> bool:
        rng = random.Random(seed)
        for _ in range(num_strategies):
            # simulate 600 independent bets at the true -5% EV with realistic-ish variance
            returns = [rng.gauss(-HOUSE_EDGE, 1.0) for _ in range(600)]
            mean = sum(returns) / len(returns)
            var = sum((x - mean) ** 2 for x in returns) / (len(returns) - 1)
            half = z * (var / len(returns)) ** 0.5
            lo, hi = mean - half, mean + half
            if not (lo <= -HOUSE_EDGE <= hi):  # the interval missed the TRUE value -- a false alarm
                return True
        return False

    trials = 300
    uncorrected_hits = sum(any_false_positive(1.96, 8, seed) for seed in range(trials))
    corrected_hits = sum(any_false_positive(bonferroni_z(8), 8, seed) for seed in range(trials))
    assert uncorrected_hits / trials > 0.15  # comfortably above the nominal 5%, as expected
    assert corrected_hits / trials < 0.12  # meaningfully brought back down toward it
