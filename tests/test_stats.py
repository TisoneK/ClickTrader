import pytest

from clicktrader.stats import (
    SampleTooSmall, chi2_sf, digit_independence, digit_uniformity, wilson_interval,
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
