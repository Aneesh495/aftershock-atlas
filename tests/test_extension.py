import numpy as np
import pytest

from aftershock.dynamic import filter_windows
from aftershock.survey_design import memberships, released_cell, replicate_estimate, symptom_scores


def test_replicate_variance_uses_full_estimate_and_census_factor():
    numerator = np.r_[30., np.full(40, 32.), np.full(40, 28.)]
    mean, se = replicate_estimate(numerator, np.full(81, 100.))
    assert mean == .3
    assert se == pytest.approx(.04)
    with pytest.raises(ValueError, match="80"):
        replicate_estimate(numerator[:-1], np.full(80, 100.))


def test_symptom_complete_items_and_source_categories():
    row = dict(ANXIOUS="2", WORRY="3", INTEREST="1", DOWN="1", EGENDER="2", RHISPANIC="1", RRACE="3")
    assert symptom_scores(row).tolist() == [1, 0, 1]
    assert memberships(row) == [0, 2, 6]
    row["DOWN"] = "-99"
    assert np.isnan(symptom_scores(row)[1:]).all()
    hidden = released_cell("small", "anxiety", 99, {"value": 40, "se": 2, "denominator": 1000, "eligible_respondents": 110})
    assert hidden["value"] is None and hidden["denominator"] is None
    assert "eligible_respondents" not in hidden


@pytest.mark.parametrize("horizon", [1, 2])
def test_dynamic_prediction_scalar_kalman_known_truth(horizon):
    parameters = np.array([0., np.log(2.), np.log(.1), np.log(.2), np.log(.3), .8])
    observed = np.array([10., 12., np.nan, 15.])
    state, covariance = np.array([0., 0.]), np.diag([.3, 2.])
    transition = np.array([[1., .8], [0., .8]])
    for t in range(1, 4 + horizon):
        state = transition @ state
        covariance = transition @ covariance @ transition.T + np.diag([.1, .2])
        if t < 4 and np.isfinite(observed[t]):
            gain = covariance[:, 0] / (covariance[0, 0] + .3)
            state += gain * (observed[t] - 10 - state[0])
            covariance -= np.outer(gain, covariance[0].copy())
    mean, variance = filter_windows(observed[None], parameters, horizon=horizon)
    assert mean[0] == pytest.approx(10 + state[0])
    assert variance[0] == pytest.approx(covariance[0, 0] + .3)
    shifted_mean, shifted_variance = filter_windows((observed + 1000)[None], parameters, horizon=horizon)
    assert shifted_mean[0] == pytest.approx(mean[0] + 1000)
    assert shifted_variance[0] == pytest.approx(variance[0])


def test_dynamic_all_missing_is_explicit():
    means, variances = filter_windows(np.full((2, 4), np.nan), np.array([0., 0., -2., -3., 0., .7]))
    assert np.isnan(means).all() and np.isnan(variances).all()
