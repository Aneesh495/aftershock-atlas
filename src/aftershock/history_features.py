"""Training-edition preprocessing and origin-specific archive features."""
from __future__ import annotations

import numpy as np

from .features import Features, OUTCOMES, held_out
from .history import edition_bound, history_cube
from .io import ROOT, read_json, write_json
from .panel import connect, records
from .resources import usage


def final_history_truth() -> dict:
    with connect() as db:
        raw = records(db, """SELECT region,metric,CAST(substr(event_start,1,4) AS INTEGER) yr,value
            FROM observations WHERE frequency='annual' AND \"group\"='total' AND value IS NOT NULL
            ORDER BY region,metric,event_start""")
    anchors = {r["region"]: r["value"] for r in raw if r["metric"] == "gdp" and r["yr"] == 2010 and r["value"] > 0}
    result = {}
    for row in raw:
        if row["metric"] not in OUTCOMES:
            continue
        value = row["value"]
        if row["metric"] == "gdp":
            if row["region"] not in anchors or value <= 0:
                continue
            value = value / anchors[row["region"]] * 100
        result.setdefault(row["region"], {}).setdefault(row["yr"], {})[row["metric"]] = value
    return result


def transformed(values: dict, region: str, year: int, metric: str) -> float:
    value = values.get(region, {}).get(year, {}).get(metric, np.nan)
    return float(np.log1p(value)) if metric == "gdp" and np.isfinite(value) else float(value)


def history_features() -> Features:
    usage(250_000_000)
    plan = read_json(ROOT / "configs/history-plan.json")
    editions = plan["editions"]
    source_by_year = {int(edition[:4]): edition for edition in editions}
    if set(source_by_year) != set(range(2018, 2024)):
        raise ValueError("Historical origin editions do not cover the registered years")
    histories = {edition: history_cube(edition)[1] for edition in editions}
    final = final_history_truth()
    initial = histories[editions[0]]
    countries = sorted(set(initial) | set(final))
    keys, raw, base, targets = [], [], [], []
    for region in countries:
        for year in list(range(2005, 2018)) + list(range(2019, 2025)):
            is_test = year >= 2019
            edition = source_by_year[year - 1] if is_test else editions[0]
            source = histories[edition]
            label_source = final if is_test else initial
            window = np.array([[transformed(source, region, y, metric) for metric in OUTCOMES]
                               for y in range(year - 5, year - 1)])
            endpoint = window[-1].copy()
            truth = np.array([transformed(label_source, region, year, metric) for metric in OUTCOMES])
            delta = truth - endpoint
            if not np.isfinite(delta).any():
                continue
            origin = f"{year - 1}-12-31T23:59:59+00:00" if is_test else None
            bound = edition_bound(edition)
            if is_test and bound > origin:
                raise ValueError("Historical feature edition follows forecast origin")
            keys.append({"region": region, "target_year": year, "feature_last_year": year - 2,
                "forecast_origin": origin, "edition": edition, "edition_available_at": bound,
                "held_out_region": held_out(region), "horizon_from_feature_endpoint": 2,
                "exercise_role": "archive_forecast" if is_test else "retrospective_training_or_validation",
                "fit_information_cutoff": "2018-12-31T23:59:59+00:00"})
            raw.append(window.ravel())
            base.append(endpoint)
            targets.append(delta)
    raw, base, target = np.array(raw), np.array(base), np.array(targets)
    mask = np.isfinite(target)
    train = np.array([k["target_year"] <= 2014 and not k["held_out_region"] for k in keys])
    validation = np.array([2015 <= k["target_year"] <= 2017 and not k["held_out_region"] for k in keys])
    test = np.array([2019 <= k["target_year"] <= 2024 for k in keys])
    if train.sum() < 200 or validation.sum() < 50 or test.sum() < 50:
        raise ValueError("Insufficient historical split support")
    center = np.nanmean(raw[train], axis=0)
    scale = np.maximum(np.nanstd(raw[train], axis=0), 1e-4)
    if not np.isfinite(center).all() or not np.isfinite(scale).all():
        raise ValueError("Unsupported historical feature column")
    x = np.concatenate([np.nan_to_num((raw - center) / scale), np.isfinite(raw).astype(float)], axis=1)
    ycenter = np.nanmean(target[train], axis=0)
    yscale = np.maximum(np.nanstd(target[train], axis=0), 1e-4)
    y = np.nan_to_num((target - ycenter) / yscale)
    counts = {region: sum(k["region"] == region and keep for k, keep in zip(keys, train)) for region in countries}
    weights = np.array([1 / max(1, counts[k["region"]]) for k in keys])
    weights /= weights[train].mean()
    features = Features(keys, raw, base, target, mask, train, validation, test, x, y,
                        center, scale, ycenter, yscale, weights)
    write_json(ROOT / "data/models/historical-v3/preprocessing.json", {**features.preprocessing(),
        "schema": "archive-two-year-index-v3", "initial_edition": editions[0],
        "training_target_years": [2005, 2014], "validation_target_years": [2015, 2017],
        "test_target_years": [2019, 2024], "forecast_horizon_from_last_feature": 2,
        "gdp_unit": "log1p within-edition real GDP per capita index, 2010=100",
        "availability": "provider-designated archive month; no original cell release-day assertion"})
    return features
