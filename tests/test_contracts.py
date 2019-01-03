import math
from pathlib import Path

import pytest

from aftershock.contracts import METRICS
from aftershock.io import atomic_path, contained, read_json, write_json


def test_signed_corrections_and_gross_enrollment():
    METRICS["covid_deaths"].validate(-40)
    METRICS["school"].validate(140)
    with pytest.raises(ValueError):
        METRICS["employment"].validate(101)
    with pytest.raises(ValueError):
        METRICS["gdp"].validate(math.inf)


def test_atomic_failure_preserves_prior_bytes(tmp_path: Path):
    p = tmp_path / "state.json"
    write_json(p, {"a": 1})
    with pytest.raises(RuntimeError):
        with atomic_path(p) as t:
            t.write_text("incomplete")
            raise RuntimeError("interruption")
    assert read_json(p) == {"a": 1}
    assert list(tmp_path.iterdir()) == [p]


def test_path_escape(tmp_path):
    with pytest.raises(ValueError):
        contained(tmp_path, "../secret")
