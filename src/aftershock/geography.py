"""Time-scoped geography and explicit population allocation uncertainty."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

import pycountry


def iso3(code: str) -> str | None:
    if code == "XK":
        return "XKX"
    obj = pycountry.countries.get(alpha_2=code)
    return obj.alpha_3 if obj else None


def us_region(name: str) -> str | None:
    if name == "United States":
        return "USA"
    if name in ("New York City", "New York City, NY"):
        return "US-NYC"
    if name in ("New York", "New York (excluding New York City)"):
        return "US-NY-EXC-NYC"
    for region in pycountry.subdivisions.get(country_code="US"):
        if region.name == name:
            return region.code
    return None


@dataclass(frozen=True)
class RegionVersion:
    id: str
    start: date
    end: date
    parent: str | None
    timezone: str | None
    population_basis: str

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def validate(self) -> None:
        if self.start > self.end:
            raise ValueError("Reversed geography interval")
        if self.timezone:
            ZoneInfo(self.timezone)


@dataclass(frozen=True)
class Allocation:
    source: str
    target: str
    weight: float
    lower: float
    upper: float


def crosswalk(values: dict[str, float], allocations: list[Allocation]) -> dict[str, dict]:
    """Only partition additive counts. Rates and survey estimates need new denominators."""
    weights: dict[str, float] = {}
    identities: set[tuple[str, str]] = set()
    for row in allocations:
        if (row.source, row.target) in identities:
            raise ValueError("Duplicate source-target allocation")
        identities.add((row.source, row.target))
        if not 0 <= row.lower <= row.weight <= row.upper <= 1:
            raise ValueError("Invalid allocation uncertainty")
        if row.source not in values or values[row.source] < 0:
            raise ValueError("Missing or negative additive count")
        weights[row.source] = weights.get(row.source, 0) + row.weight
    if set(values) != set(weights) or any(abs(w - 1) > 1e-10 for w in weights.values()):
        raise ValueError("Crosswalk must conserve every source population exactly once")
    output: dict[str, dict] = {}
    for row in allocations:
        out = output.setdefault(row.target, {"value": 0.0, "lower": 0.0, "upper": 0.0})
        for key, weight in (("value", row.weight), ("lower", row.lower), ("upper", row.upper)):
            out[key] += values[row.source] * weight
    return output


def rate(count: float, denominator: float, scale: float = 100_000) -> float:
    if denominator <= 0 or scale <= 0:
        raise ValueError("Positive denominator and scale required")
    return count / denominator * scale


def age_standardized(counts: list[float], populations: list[float], weights: list[float]) -> dict:
    import numpy as np
    if not len(counts) == len(populations) == len(weights) or not counts:
        raise ValueError("Age bands must be identical and nonempty")
    c, p, w = (np.asarray(x, dtype=float) for x in (counts, populations, weights))
    if not all(np.isfinite(x).all() for x in (c, p, w)) or (c < 0).any() or (p <= 0).any() or (w < 0).any():
        raise ValueError("Invalid age-specific quantities")
    if not np.isclose(w.sum(), 1, atol=1e-12, rtol=0):
        raise ValueError("Standard population weights must sum to one")
    value = float(np.sum(w * c / p) * 100_000)
    variance = float(np.sum(w ** 2 * c / p ** 2) * 100_000 ** 2)
    return {"rate": value, "se": variance ** .5, "method": "direct; Poisson event variance",
            "unit": "deaths/100000 standard population"}
