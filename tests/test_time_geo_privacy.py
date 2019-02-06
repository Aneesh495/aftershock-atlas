from datetime import date

import pytest

from aftershock.geography import Allocation, age_standardized, crosswalk, us_region
from aftershock.privacy import Disclosure
from aftershock.temporal import Phase, as_of, validate_phases


def test_independent_age_oracle():
    out = age_standardized([10, 60], [10000, 20000], [.4, .6])
    assert out["rate"] == pytest.approx(220)
    assert out["se"] ** 2 == pytest.approx(700)


def test_partition_population_conservation():
    alloc = [Allocation("old", "a", .25, .2, .3), Allocation("old", "b", .75, .7, .8)]
    out = crosswalk({"old": 100}, alloc)
    assert out["a"]["value"] == 25 and out["b"]["value"] == 75
    with pytest.raises(ValueError, match="conserve"):
        crosswalk({"old": 100}, alloc[:1])
    assert us_region("New York") != us_region("New York City")
    assert us_region("New York") == "US-NY"
    assert us_region("New York", occurrence_series=True) == "US-NY-EXC-NYC"


def test_vintage_does_not_look_ahead():
    base = dict(region="USA", metric="covid_deaths", event_start="2020-03-01", event_end="2020-03-07", group="total")
    rows = [{**base, "value": 10, "available_at": "2020-03-08T00:00:00+00:00", "vintage": "2020-03-08T00:00:00+00:00"},
            {**base, "value": 12, "available_at": "2020-03-20T00:00:00+00:00", "vintage": "2020-03-20T00:00:00+00:00"}]
    assert as_of(rows, "2020-03-10T00:00:00Z")[0]["value"] == 10
    assert as_of(rows, "2020-03-01T00:00:00Z") == []
    with pytest.raises(ValueError, match="Duplicate"):
        as_of(rows * 2, "2020-04-01T00:00:00Z")


def test_overlap_phases_rejected():
    with pytest.raises(ValueError):
        validate_phases([Phase("A", "employment", "a", date(2020, 1, 1), date(2020, 2, 1), "source"),
                         Phase("A", "employment", "b", date(2020, 2, 1), date(2020, 3, 1), "source")])


def test_suppression_holds_for_export_and_complements():
    policy = Disclosure()
    rows = [{"group": "x", "value": 10, "sample_n": 5, "lower": 8, "upper": 12},
            {"group": "y", "value": 50, "sample_n": 100}]
    out = policy.table(rows, exhaustive=True)
    assert all(row["value"] is None for row in out)
    assert out[0]["lower"] is None and "sample_n" not in out[0]
    assert policy.apply(out[0]) == out[0]
