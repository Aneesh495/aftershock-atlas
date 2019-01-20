import pytest

from aftershock.causal import group_time
from aftershock.survey import nonresponse_envelope, weighted_mean


def test_did_known_truth_and_unsupported_comparison():
    panel, dates = {}, {}
    for i in range(20):
        dates[str(i)] = 2020 if i < 10 else None
        panel[str(i)] = {2019: 40 + i, 2020: 41 + i + (3 if i < 10 else 0)}
    out = group_time(panel, dates, 2020, 2020)
    assert out["effect"] == 3 and out["lower"] == out["upper"] == 3
    out = group_time(panel, dict.fromkeys(dates, 2020), 2020, 2020)
    assert out["effect"] is None and out["control_n"] == 0


def test_weighted_design_independent_oracle():
    result = weighted_mean([0, 1, 0, 1], [1, 1, 2, 2], ["a", "b", "c", "d"], ["s", "s", "t", "t"])
    assert result["mean"] == .5
    assert result["se"] ** 2 == pytest.approx(5 / 36)
    assert result["kish_effective_n"] == pytest.approx(3.6)
    assert nonresponse_envelope(.4, .1) == pytest.approx((.04, .94))
    with pytest.raises(ValueError, match="Singleton"):
        weighted_mean([1], [1], ["a"], ["s"])
