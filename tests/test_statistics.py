import math

import numpy as np
import pytest

from aftershock.statistics import (bh_adjust, conformal_multiplier, fit_negative_binomial,
                                  interrupted_time_series, local_level, proper_scores, ridge)


def test_analytical_scores():
    out = proper_scores([0], [0], [1])
    assert out["gaussian_nll"] == pytest.approx(math.log(2 * math.pi) / 2)
    assert out["crps"] == pytest.approx((math.sqrt(2) - 1) / math.sqrt(math.pi))
    assert out["coverage_90"] == 1
    with pytest.raises(ValueError):
        proper_scores([0], [0], [0])


def test_regression_and_count_mean():
    x = np.column_stack([np.ones(40), np.arange(40)])
    assert ridge(x, x @ np.array([3, 2]), penalty=0) == pytest.approx([3, 2])
    fit = fit_negative_binomial(np.ones((40, 1)), np.full(40, 5))
    mean, sd = fit.predict(np.ones((1, 1)))
    assert mean[0] == pytest.approx(5, abs=1e-6) and sd[0] > 0
    with pytest.raises(ValueError):
        fit_negative_binomial(np.ones((2, 1)), [-1, 2])


def test_state_filter_carries_missing_without_future():
    a, v, trace = local_level([1, 1, np.nan, 9])
    assert trace[2]["state"] == 1 and trace[2]["variance"] > trace[1]["variance"]
    assert 1 < a < 9 and v > 0


def test_its_recovers_known_level_and_bh_oracle():
    x = np.arange(80)
    y = 4 + .2 * x + 8 * (x >= 40)
    result = interrupted_time_series(y, 40)
    assert result["level_change"] == pytest.approx(8, abs=1e-4)
    assert bh_adjust([.01, .04, .03]) == pytest.approx([.03, .04, .04])
    assert conformal_multiplier(np.arange(10), np.arange(10), np.ones(10)) == .01
