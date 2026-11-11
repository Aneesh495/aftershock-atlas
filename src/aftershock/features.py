"""Chronological features, outcome masks and country-frozen fitting populations."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from .io import ROOT, write_json
from .panel import connect, records

OUTCOMES = ("employment", "gdp", "school", "immunization", "mortality", "life_expectancy")
SEEDS = (11, 29, 47)


def held_out(region: str) -> bool:
    return int(hashlib.sha256(region.encode()).hexdigest(), 16) % 5 == 0


def transform(value: np.ndarray | float, outcome: str):
    return np.log1p(value) if outcome == "gdp" else value


def inverse(value: np.ndarray | float, outcome: str):
    return np.expm1(np.clip(value, -20, 25)) if outcome == "gdp" else value


@dataclass
class Features:
    keys: list[dict]
    raw: np.ndarray
    base: np.ndarray
    target: np.ndarray
    mask: np.ndarray
    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray
    x: np.ndarray
    y: np.ndarray
    xmean: np.ndarray
    xscale: np.ndarray
    ymean: np.ndarray
    yscale: np.ndarray
    weights: np.ndarray

    def preprocessing(self) -> dict:
        return {"xmean": self.xmean.tolist(), "xscale": self.xscale.tolist(),
                "ymean": self.ymean.tolist(), "yscale": self.yscale.tolist(), "outcomes": OUTCOMES,
                "feature_order": "four annual lags, oldest first, each with six outcomes; then missing masks",
                "train": [self.keys[i] for i in np.where(self.train)[0]],
                "validation": [self.keys[i] for i in np.where(self.validation)[0]],
                "test": [self.keys[i] for i in np.where(self.test)[0]]}


def annual_cube() -> tuple[list[str], np.ndarray]:
    with connect() as db:
        rows = records(db, """SELECT region,metric,CAST(substr(event_start,1,4) AS INTEGER) year,value
            FROM observations WHERE frequency='annual' AND \"group\"='total' AND value IS NOT NULL
            AND length(region)=3 ORDER BY region,year,metric""")
    regions = sorted({r["region"] for r in rows})
    lookup = {r: i for i, r in enumerate(regions)}
    cube = np.full((len(regions), 26, len(OUTCOMES)), np.nan)
    for r in rows:
        if r["metric"] in OUTCOMES and 2000 <= r["year"] <= 2025:
            j = OUTCOMES.index(r["metric"])
            index = (lookup[r["region"]], r["year"] - 2000, j)
            if np.isfinite(cube[index]):
                raise ValueError("Duplicate annual population")
            cube[index] = transform(r["value"], r["metric"])
    return regions, cube


def make_features() -> Features:
    regions, cube = annual_cube()
    keys, raw, bases, targets = [], [], [], []
    for region_index, region in enumerate(regions):
        for year in range(2004, 2025):
            pos = year - 2000
            window = cube[region_index, pos - 4:pos]
            base = window[-1].copy()
            target = cube[region_index, pos] - base
            if not np.isfinite(target).any() or not np.isfinite(window).any():
                continue
            keys.append({"region": region, "target_year": year, "feature_last_year": year - 1,
                         "held_out_region": held_out(region)})
            raw.append(window.flatten()); bases.append(base); targets.append(target)
    raw, base, target = np.array(raw), np.array(bases), np.array(targets)
    mask = np.isfinite(target)
    train = np.array([k["target_year"] <= 2015 and not k["held_out_region"] for k in keys])
    validation = np.array([2016 <= k["target_year"] <= 2018 and not k["held_out_region"] for k in keys])
    test = np.array([2019 <= k["target_year"] <= 2024 for k in keys])
    if train.sum() < 200 or validation.sum() < 50 or test.sum() < 50:
        raise ValueError("Insufficient split support")
    xmean, xscale = np.nanmean(raw[train], axis=0), np.nanstd(raw[train], axis=0)
    xscale = np.maximum(xscale, 1e-4)
    x = np.concatenate([np.nan_to_num((raw - xmean) / xscale), np.isfinite(raw).astype(float)], axis=1)
    ymean, yscale = np.nanmean(target[train], axis=0), np.maximum(np.nanstd(target[train], axis=0), 1e-4)
    y = np.nan_to_num((target - ymean) / yscale)
    counts = {r: sum(k["region"] == r and t for k, t in zip(keys, train)) for r in regions}
    weights = np.array([1 / max(1, counts[k["region"]]) for k in keys])
    weights /= weights[train].mean()
    result = Features(keys, raw, base, target, mask, train, validation, test, x, y,
                      xmean, xscale, ymean, yscale, weights)
    write_json(ROOT / "data/models/preprocessing.json", result.preprocessing())
    return result
