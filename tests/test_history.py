import copy

import pytest

from aftershock.history import edition_bound, validate_archive


def archive_fixture():
    rows = [{"variable": [{"concept": "Country", "id": f"C{i}", "value": f"country {i}"},
                         {"concept": "Version", "id": "201811", "value": "2018 Nov"},
                         {"concept": "Series", "id": "SP.POP.TOTL", "value": "Population"},
                         {"concept": "Time", "id": "YR2010", "value": "2010"}], "value": 100 + i}
            for i in range(100)]
    return {"page": 1, "pages": 1, "total": 100, "source": {"id": "57", "data": rows}}


def test_archive_month_bound_is_explicit_and_handles_leap_years():
    assert edition_bound("202002") == "2020-02-29T23:59:59+00:00"
    assert edition_bound("201802") == "2018-02-28T23:59:59+00:00"
    for bad in ("201813", "20181", "future", "180001"):
        with pytest.raises(ValueError):
            edition_bound(bad)


def test_archive_rejects_partial_pages_and_edition_substitution():
    data = archive_fixture()
    assert len(validate_archive(data, "201811", "SP.POP.TOTL")) == 100
    data["pages"] = 2
    with pytest.raises(ValueError, match="pagination"):
        validate_archive(data, "201811", "SP.POP.TOTL")
    data["pages"] = 1
    with pytest.raises(ValueError, match="substituted"):
        validate_archive(data, "201912", "SP.POP.TOTL")
    data["source"]["data"][1] = copy.deepcopy(data["source"]["data"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_archive(data, "201811", "SP.POP.TOTL")
