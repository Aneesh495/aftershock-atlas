"""Independent archive parsing, feature reconstruction and prediction replay."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np
import pyarrow.parquet as pq
from scipy.special import erf

from .io import ROOT, contained, digest, read_json
from .verification import require, verify_array_archive
from .verification_extension import scalar_dynamic

OUTCOMES = ("employment", "gdp", "school", "immunization", "mortality", "life_expectancy")


def month_bound(edition):
    y, m = int(edition[:4]), int(edition[4:])
    last = date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)
    return last.isoformat() + "T23:59:59+00:00"


def independent_archives(bundle):
    pins = read_json(ROOT / "configs/history-inputs.json")
    supplied = read_json(bundle / "HISTORY_INPUTS.json")
    plan = read_json(ROOT / "configs/history-plan.json")
    require(set(pins) == set(supplied), "Historical source population changed")
    core = read_json(bundle / "DATASETS.json")["sources"]["regions"]
    registry = read_json(bundle / core["bundle_path"])[1]
    countries = {r["id"] for r in registry if r["region"]["id"] != "NA"}
    values, raw_values, labels = {}, {}, {}
    future = 0
    for source_id, expected in pins.items():
        record = supplied[source_id]
        require({k: v for k, v in record.items() if k != "bundle_path"} == expected, "Historical source metadata mismatch")
        path = contained(bundle, record["bundle_path"])
        require(digest(path) == expected["sha256"], "Historical upstream byte identity mismatch")
        payload = read_json(path, 12_000_000)
        require(payload.get("page") == 1 and payload.get("pages") == 1, "Historical raw pagination incomplete")
        if source_id == "history_catalogue":
            available = {r["id"] for r in payload["source"][0]["concept"][0]["variable"]}
            require(set(plan["editions"]) <= available, "Unknown provider archive edition")
            continue
        _, edition, metric = source_id.split("_", 2)
        require(payload["source"]["id"] == "57", "Historical raw source substituted")
        data = payload["source"]["data"]
        require(len(data) == payload["total"], "Historical raw population omitted")
        seen = set()
        partition = {}
        for row in data:
            dimensions = {d["concept"]: d for d in row["variable"]}
            require(len(row["variable"]) == 4 and set(dimensions) == {"Country", "Series", "Time", "Version"}, "Historical raw dimensions changed")
            require(dimensions["Version"]["id"] == edition and dimensions["Series"]["id"] == plan["series"][metric], "Historical raw edition substituted")
            region, year = dimensions["Country"]["id"], int(dimensions["Time"]["id"][2:])
            require((region, year) not in seen, "Duplicate historical raw population")
            seen.add((region, year))
            value = row.get("value")
            require(value is None or (isinstance(value, (int, float)) and math.isfinite(value)), "Nonfinite historical raw value")
            if region in countries:
                partition[region, year] = value
                labels[edition, metric] = dimensions["Series"].get("value", "")
        for (region, year), value in partition.items():
            if not 2000 <= year <= 2024:
                continue
            key = edition, region, metric, year
            raw_values[key] = value
            if year > int(edition[:4]):
                future += value is not None
                value = None
            if metric == "gdp":
                anchor = partition.get((region, 2010))
                value = value / anchor * 100 if value is not None and anchor is not None and anchor > 0 else None
            values[key] = value
    anchors = read_json(bundle / "history-anchors.json")
    require(len(anchors) == len(plan["editions"]) * len(countries), "Historical GDP anchor population mismatch")
    anchor_keys = set()
    for row in anchors:
        key = row["edition"], row["region"], "gdp", 2010
        require(key not in anchor_keys, "Duplicate historical GDP anchor")
        anchor_keys.add(key)
        require(row["raw_2010"] == raw_values.get(key), "Historical GDP anchor detached from raw edition")
        require(row["source_sha256"] == pins[f"archive_{row['edition']}_gdp"]["sha256"], "Historical GDP anchor source mismatch")
    actual = set()
    for batch in pq.ParquetFile(bundle / "history-observations.parquet").iter_batches(batch_size=8192):
        for row in batch.to_pylist():
            key = row["edition"], row["region"], row["metric"], row["year"]
            require(key in values and key not in actual, "Historical serialized population mismatch")
            actual.add(key)
            expected, value = values[key], row["value"]
            require((expected is None and value is None) or (expected is not None and value is not None and math.isclose(expected, value, rel_tol=1e-12)), "Historical value replay mismatch")
            require(row["raw_value"] == raw_values[key], "Historical raw value changed during serialization")
            require(row["edition_available_at"] == month_bound(row["edition"]), "Forged historical edition bound")
            require(row["source_hash"] == pins[f"archive_{row['edition']}_{row['metric']}"]["sha256"], "Historical serialized source mismatch")
            if row["metric"] == "gdp":
                require(row["anchor_2010"] == raw_values.get((row["edition"], row["region"], "gdp", 2010)), "Historical GDP anchor serialization mismatch")
                require(row["unit"] == "2010=100 within-edition real GDP per capita index" and row["kind"] == "derived_index", "Historical GDP unit reclassified")
    require(actual == set(values), "Historical raw observations omitted from serialized panel")
    manifest = read_json(bundle / "history-manifest.json")
    require(len(actual) == manifest["rows"] and future == sum(r["excluded_future_values"] for r in manifest["inventory"]), "Historical coverage or future-value count mismatch")
    require(digest(bundle / "history-observations.parquet") == manifest["sha256"], "Historical panel identity mismatch")
    revisions = read_json(bundle / "history-revisions.json")
    early, late = plan["editions"][0], plan["editions"][-1]
    expected_revision_keys = {(region, metric, year) for edition, region, metric, year in values if edition == early and year <= 2017}
    revision_keys = set()
    for row in revisions["rows"]:
        key = row["region"], row["metric"], row["year"]
        require(key not in revision_keys, "Duplicate historical revision comparison")
        revision_keys.add(key)
        a, b = values.get((early, *key)), values.get((late, *key))
        require(row["old_value"] == a and row["new_value"] == b, "Historical revision detached from raw editions")
        change = b - a if a is not None and b is not None else None
        require(row["change"] == change, "Historical revision subtraction mismatch")
    require(revision_keys == expected_revision_keys, "Historical revision population omitted")
    for summary in revisions["summaries"]:
        changes = np.array([r["change"] for r in revisions["rows"] if r["metric"] == summary["metric"] and r["change"] is not None])
        require(summary["matched_cells"] == len(changes), "Historical revision denominator mismatch")
        expected_summary = {"unmatched_cells": sum(r["metric"] == summary["metric"] and r["change"] is None for r in revisions["rows"]),
            "exactly_changed_cells": int(np.sum(changes != 0)), "median_signed_revision": float(np.median(changes)),
            "median_absolute_revision": float(np.median(abs(changes))), "p95_absolute_revision": float(np.quantile(abs(changes), .95))}
        require(all(math.isclose(summary[name], value, abs_tol=1e-10) for name, value in expected_summary.items()), "Historical revision summary mismatch")
    expected_signs = {}
    for region in countries:
        for metric in plan["series"]:
            endpoints = [values.get((edition, region, metric, year)) for edition in (early, late) for year in (2010, 2017)]
            if any(value is None for value in endpoints):
                continue
            a, b = endpoints[1] - endpoints[0], endpoints[3] - endpoints[2]
            expected_signs[region, metric] = a, b, a * b < 0
    require(len(revisions["trajectory_signs"]) == len(expected_signs), "Historical direction population mismatch")
    seen_signs = set()
    for row in revisions["trajectory_signs"]:
        key = row["region"], row["metric"]
        require(key not in seen_signs and key in expected_signs, "Historical direction population substituted")
        seen_signs.add(key)
        a, b, opposite = expected_signs[key]
        require(row["change_2010_2017_old"] == a and row["change_2010_2017_new"] == b and row["opposite_nonzero_directions"] == opposite,
                "Historical trajectory direction mismatch")
    return values, countries, {"source_partitions": len(pins), "serialized_cells": len(actual), "future_reference_values_excluded": future,
                               "revision_comparisons": len(revision_keys)}


def verify_historical_features(bundle, values, countries, annual):
    plan = read_json(ROOT / "configs/history-plan.json")
    initial = plan["editions"][0]
    editions = {int(e[:4]): e for e in plan["editions"]}
    keys = read_json(bundle / "models/historical-v3/replay-keys.json")
    preprocessing = read_json(bundle / "models/historical-v3/preprocessing.json")
    def held(region):
        return int(hashlib.sha256(region.encode()).hexdigest(), 16) % 5 == 0
    def historic(edition, region, metric, year):
        value = values.get((edition, region, metric, year))
        return (math.log1p(value) if metric == "gdp" else value) if value is not None else math.nan
    def truth(region, metric, year, is_test):
        if not is_test:
            return historic(initial, region, metric, year)
        value = annual.get((region, metric, year))
        if metric == "gdp":
            anchor = annual.get((region, metric, 2010))
            value = value / anchor * 100 if value is not None and anchor is not None and anchor > 0 else None
        return (math.log1p(value) if metric == "gdp" else value) if value is not None else math.nan
    expected_keys, raw, targets, bases = [], [], [], []
    for region in sorted(countries):
        for year in list(range(2005, 2018)) + list(range(2019, 2025)):
            is_test = year >= 2019
            edition = editions[year - 1] if is_test else initial
            window = [historic(edition, region, metric, y) for y in range(year - 5, year - 1) for metric in OUTCOMES]
            endpoint = window[-6:]
            target = [truth(region, metric, year, is_test) - endpoint[j] for j, metric in enumerate(OUTCOMES)]
            if not any(math.isfinite(t) for t in target):
                continue
            expected_keys.append((region, year, edition))
            raw.append(window)
            bases.append(endpoint)
            targets.append(target)
    require([(k["region"], k["target_year"], k["edition"]) for k in keys] == expected_keys, "Historical feature population or edition substituted")
    for key in keys:
        year = key["target_year"]
        require(key["feature_last_year"] == year - 2 and key["horizon_from_feature_endpoint"] == 2, "Future historical feature label")
        require(key["edition_available_at"] == month_bound(key["edition"]), "Forged historical edition bound")
        require(key["held_out_region"] == held(key["region"]), "Historical held-out country reclassified")
        if year >= 2019:
            require(key["forecast_origin"] == f"{year-1}-12-31T23:59:59+00:00" and key["edition_available_at"] <= key["forecast_origin"], "Historical edition follows origin")
        else:
            require(key["edition"] == initial and key["forecast_origin"] is None, "Historical training information set changed")
    raw, base, target = np.array(raw), np.array(bases), np.array(targets)
    train = np.array([k["target_year"] <= 2014 and not held(k["region"]) for k in keys])
    validation = np.array([2015 <= k["target_year"] <= 2017 and not held(k["region"]) for k in keys])
    test = np.array([k["target_year"] >= 2019 for k in keys])
    mask = np.isfinite(target)
    center, scale = np.nanmean(raw[train], axis=0), np.maximum(np.nanstd(raw[train], axis=0), 1e-4)
    ymean, yscale = np.nanmean(target[train], axis=0), np.maximum(np.nanstd(target[train], axis=0), 1e-4)
    require(np.allclose(center, preprocessing["xmean"]) and np.allclose(scale, preprocessing["xscale"]), "Historical normalizer uses wrong edition or population")
    x = np.concatenate([np.nan_to_num((raw - center) / scale), np.isfinite(raw).astype(float)], axis=1)
    expected = {"x": x, "raw": raw, "base": base, "target": target, "mask": mask, "train": train,
                "validation": validation, "test": test, "ymean": ymean, "yscale": yscale}
    with np.load(bundle / "models/historical-v3/replay-inputs.npz", allow_pickle=False) as stored:
        require(set(stored.files) == set(expected), "Historical replay arrays changed")
        for name, array in expected.items():
            require(stored[name].shape == array.shape and np.allclose(stored[name], array, equal_nan=True), "Historical replay inputs differ from raw archives: " + name)
    counts = Counter(k["region"] for k, keep in zip(keys, train) if keep)
    weights = np.array([1 / max(1, counts[k["region"]]) for k in keys])
    weights /= weights[train].mean()
    return {**expected, "keys": keys, "weights": weights}


def verify_vintage_sensitivity(bundle, values, countries, annual):
    plan = read_json(ROOT / "configs/history-plan.json")
    editions = {int(e[:4]): e for e in plan["editions"]}
    rows = read_json(bundle / "history-sensitivity.json")
    expected = {(region, metric, year) for region in countries for metric in OUTCOMES for year in range(2019, 2025)}
    seen = set()
    for row in rows:
        region, metric, year = row["region"], row["metric"], row["target_year"]
        key = region, metric, year
        require(key in expected and key not in seen, "Historical sensitivity population substituted")
        seen.add(key)
        edition, endpoint = editions[year - 1], year - 2
        require(row["edition"] == edition and row["endpoint_year"] == endpoint, "Historical sensitivity chronology mismatch")
        a = values.get((edition, region, metric, endpoint))
        b = values.get((plan["editions"][0], region, metric, endpoint))
        c = annual.get((region, metric, endpoint))
        if metric == "gdp":
            anchor = annual.get((region, metric, 2010))
            c = c / anchor * 100 if c is not None and anchor is not None and anchor > 0 else None
            a, b, c = [math.log1p(v) if v is not None else None for v in (a, b, c)]
        expected_values = {"archived_endpoint_t": a, "initial_edition_endpoint_t": b, "current_endpoint_t": c,
                           "current_minus_archived_t": c - a if c is not None and a is not None else None}
        for name, value in expected_values.items():
            supplied = row[name]
            require((value is None and supplied is None) or (value is not None and supplied is not None and math.isclose(value, supplied, abs_tol=1e-10)),
                    "Historical sensitivity detached from source editions")
    require(seen == expected, "Historical sensitivity population omitted")
    return len(rows)


def independently_score(rows, scores):
    groups = defaultdict(list)
    for r in rows:
        for group in ("all", "held_out_country" if r["held_out_region"] else "retained_country", "country:" + r["region"], "year:" + str(r["target_year"])):
            groups[r["model"], r["metric"], group].append(r)
    supplied = {(r["model"], r["metric"], r["group"]): r for r in scores}
    require(len(supplied) == len(scores) and set(supplied) == set(groups), "Historical score populations omitted")
    for key, population in groups.items():
        score = supplied[key]
        require(score["n"] == len(population), "Historical score denominator mismatch")
        y, mu, sd, lower, upper = [np.array([r[field] for r in population]) for field in ("truth_t", "mean_t", "sd_t", "lower_t", "upper_t")]
        require(np.isfinite([y, mu, sd, lower, upper]).all() and (sd > 0).all(), "Invalid historical predictive distribution")
        z = (y - mu) / sd
        cdf, pdf = .5 * (1 + erf(z / math.sqrt(2))), np.exp(-z * z / 2) / math.sqrt(2 * math.pi)
        recomputed = {"crps": float(np.mean(sd * (z * (2 * cdf - 1) + 2 * pdf - 1 / math.sqrt(math.pi)))),
            "gaussian_nll": float(np.mean(np.log(sd) + .5 * math.log(2 * math.pi) + z * z / 2)),
            "mae": float(np.mean(abs(y - mu))), "rmse": float(np.mean((y - mu) ** 2) ** .5),
            "coverage_90": float(np.mean((y >= lower) & (y <= upper))), "width_90": float(np.mean(upper - lower)),
            "interval_score_90": float(np.mean(upper - lower + 20 * np.maximum(lower - y, 0) + 20 * np.maximum(y - upper, 0)))}
        for name, value in recomputed.items():
            require(math.isclose(value, score[name], rel_tol=1e-9, abs_tol=1e-9), "Historical proper score mismatch: " + name)
    return len(groups)


def verify_history(bundle, annual):
    for path in (bundle / "models/historical-v3").rglob("*.npz"):
        verify_array_archive(path)
    values, countries, checks = independent_archives(bundle)
    checks["sensitivity_cells"] = verify_vintage_sensitivity(bundle, values, countries, annual)
    f = verify_historical_features(bundle, values, countries, annual)
    fit = read_json(bundle / "history-fit.json")
    require(fit["protocol"] == "historical-v3-exploratory", "Historical exercise relabeled confirmatory")
    require(fit["identity"]["protocol"] == digest(ROOT / "docs/HISTORICAL_PLAN_V3.md"), "Historical protocol mismatch")
    require(fit["identity"]["archive_panel"] == read_json(bundle / "history-manifest.json")["sha256"], "Historical model input panel mismatch")
    for name, checksum in fit["identity"]["model_code"].items():
        require(digest(ROOT / "src/aftershock" / name) == checksum, "Historical checkpoint code identity mismatch")
    predictions = []
    for metric in OUTCOMES:
        path = bundle / "history-predictions" / f"{metric}.json"
        require(digest(path) == fit["prediction_files"][metric]["sha256"], "Historical prediction partition identity mismatch")
        predictions.extend(read_json(path))
    key_lookup = {(k["region"], k["target_year"]): i for i, k in enumerate(f["keys"])}
    seen = set()
    model_rows = defaultdict(dict)
    for row in predictions:
        identity = row["model"], row["region"], row["target_year"], row["metric"]
        require(identity not in seen, "Duplicate historical forecast population")
        seen.add(identity)
        i = key_lookup[row["region"], row["target_year"]]
        j = OUTCOMES.index(row["metric"])
        key = f["keys"][i]
        require(f["test"][i] and f["mask"][i, j], "Historical forecast outside eligible population")
        require(row["feature_last_year"] == row["target_year"] - 2, "Future historical feature label")
        require(row["edition_available_at"] == month_bound(row["edition"]), "Forged historical edition bound")
        require(row["edition_available_at"] <= row["forecast_origin"], "Historical edition follows origin")
        require(all(row[k] == key[k] for k in key), "Historical feature edition substituted")
        require(row["availability_mode"] == "provider_designated_archive", "Historical availability basis relabeled")
        require(math.isclose(row["truth_t"], f["target"][i, j] + f["base"][i, j], abs_tol=1e-9), "Historical target detached from source")
        require(math.isclose(row["feature_endpoint_t"], f["base"][i, j], abs_tol=1e-9), "Historical endpoint uses final-vintage fallback")
        radius = row["sd_t"] * row["calibration_multiplier"]
        require(math.isclose(row["lower_t"], row["mean_t"] - radius, abs_tol=1e-9) and
                math.isclose(row["upper_t"], row["mean_t"] + radius, abs_tol=1e-9), "Historical predictive interval detached from calibration")
        model_rows[row["model"]][i, j] = row
    expected_cells = {(i, j) for i in np.where(f["test"])[0] for j in range(6) if f["mask"][i, j]}
    require(len(model_rows) == 11 and all(set(rows) == expected_cells for rows in model_rows.values()), "Historical model populations differ")
    require({r["model"] for r in fit["scores"] if r["group"] == "all"} == set(model_rows) and
            len([r for r in fit["scores"] if r["group"] == "all"]) == 66, "Historical completed configuration count mismatch")
    score_groups = independently_score(predictions, fit["scores"])
    # Saved parameters are replayed without invoking any training implementation.
    for seed in (11, 29, 47):
        with np.load(bundle / f"models/historical-v3/seed-{seed}/best.npz", allow_pickle=False) as best, np.load(
                bundle / f"models/historical-v3/seed-{seed}/initial.npz", allow_pickle=False) as initial:
            movement = sum(float(np.sum((best["p_" + name] - initial["p_" + name]) ** 2)) for name in ("w1", "b1", "w2", "b2"))
            state = json.loads(best["state"].tobytes())
            require(movement > 1e-12 and state["steps"] > 0 and state["epoch"] > 0, "Historical network never trained")
            require(state["extra"]["identity"] == fit["identity"], "Historical checkpoint data identity mismatch")
            rng = np.random.default_rng(seed)
            expected_w1 = rng.normal(0, 1 / math.sqrt(48), (48, 48))
            expected_w2 = rng.normal(0, .1 / math.sqrt(48), (48, 12))
            require(np.array_equal(initial["p_w1"], expected_w1) and np.array_equal(initial["p_w2"], expected_w2), "Historical initialization was not the declared fresh seed")
        for filename, model_name in (("best.npz", f"network_{seed}"), ("initial.npz", f"untrained_{seed}")):
            with np.load(bundle / f"models/historical-v3/seed-{seed}/{filename}", allow_pickle=False) as checkpoint:
                hidden = np.tanh(f["x"] @ checkpoint["p_w1"] + checkpoint["p_b1"])
                out = hidden @ checkpoint["p_w2"] + checkpoint["p_b2"]
                mean = out[:, :6] * f["yscale"] + f["ymean"]
                sd = np.exp(.5 * np.clip(out[:, 6:], -6, 3)) * f["yscale"]
            for (i, j), row in model_rows[model_name].items():
                require(math.isclose(row["mean_t"], mean[i, j] + f["base"][i, j], abs_tol=1e-8), "Historical saved-model mean replay failed")
                require(math.isclose(row["sd_t"], sd[i, j], abs_tol=1e-8), "Historical saved-model variance replay failed")
            for j in range(6):
                selected = f["validation"] & f["mask"][:, j]
                residuals = np.sort(abs(f["target"][selected, j] - mean[selected, j]) / sd[selected, j])
                multiplier = max(.01, residuals[min(len(residuals) - 1, math.ceil((len(residuals) + 1) * .9) - 1)])
                for (i, column), row in model_rows[model_name].items():
                    if column == j:
                        require(math.isclose(row["calibration_multiplier"], multiplier, abs_tol=1e-8), "Historical calibration uses wrong information set")
    for j, metric in enumerate(OUTCOMES):
        parameters = next(p for p in fit["baseline_parameters"] if p["metric"] == metric)
        selected = f["train"] & f["mask"][:, j]
        noise = max(float(np.std(f["target"][selected, j])), 1e-3)
        require(math.isclose(noise, parameters["noise"], abs_tol=1e-10), "Historical baseline noise uses wrong training population")
        design = np.column_stack([np.ones(len(f["x"])), f["x"]])
        beta = np.array(parameters["ridge_beta"])
        residual = f["target"][selected, j] - design[selected] @ beta
        normal = design[selected].T @ (f["weights"][selected] * residual)
        normal[1:] -= beta[1:]
        require(np.linalg.norm(normal) < 1e-6, "Historical ridge normal equations fail")
        require(math.isclose(parameters["ridge_residual_sd"], max(float(np.std(residual)), 1e-3), abs_tol=1e-9), "Historical ridge residual scale mismatch")
        classical = {name: (np.zeros(len(f["x"])), np.full(len(f["x"]), noise)) for name in
                     ("persistence", "trend", "pooled_ridge", "local_level", "hierarchical_damped_2y")}
        classical["pooled_ridge"] = (design @ beta, np.full(len(f["x"]), parameters["ridge_residual_sd"]))
        for i, flattened in enumerate(f["raw"]):
            window = flattened.reshape(4, 6)[:, j]
            valid = np.isfinite(window)
            if not valid[-1]:
                continue
            if valid.sum() >= 3:
                times, observations = np.arange(4)[valid], window[valid]
                slope = float(np.sum((times - times.mean()) * (observations - observations.mean())) /
                              (np.sum((times - times.mean()) ** 2) + 1e-5))
                classical["trend"][0][i] = observations.mean() + slope * (5 - times.mean()) - window[-1]
            state, variance = float(window[valid][0]), 10 * noise ** 2
            for observation in window:
                variance += noise ** 2 * .1
                if math.isfinite(observation):
                    gain = variance / (variance + noise ** 2)
                    state += gain * (observation - state)
                    variance *= 1 - gain
            classical["local_level"][0][i] = state - window[-1]
            classical["local_level"][1][i] = math.sqrt(variance + 2 * noise ** 2 * .1 + noise ** 2)
        dynamic = parameters["dynamic"]["chosen"]
        likelihood, weights = [], []
        for i in np.where(selected)[0]:
            window = f["raw"][i].reshape(4, 6)[:, j] / f["yscale"][j]
            mu, variance = scalar_dynamic(window, dynamic["parameters"], horizon=2)
            truth = (f["target"][i, j] + f["base"][i, j]) / f["yscale"][j]
            likelihood.append(.5 * (math.log(2 * math.pi * variance) + (truth - mu) ** 2 / variance))
            weights.append(f["weights"][i])
        require(math.isclose(float(np.average(likelihood, weights=weights)), dynamic["training_nll"], abs_tol=1e-8), "Historical dynamic training likelihood mismatch")
        for i in np.where(f["mask"][:, j])[0]:
            mu, variance = scalar_dynamic(f["raw"][i].reshape(4, 6)[:, j] / f["yscale"][j], dynamic["parameters"], horizon=2)
            classical["hierarchical_damped_2y"][0][i] = mu * f["yscale"][j] - f["base"][i, j]
            classical["hierarchical_damped_2y"][1][i] = math.sqrt(variance) * f["yscale"][j]
        for name, (means, spreads) in classical.items():
            validation = f["validation"] & f["mask"][:, j]
            residuals = np.sort(abs(f["target"][validation, j] - means[validation]) / spreads[validation])
            calibration = max(.01, residuals[min(len(residuals) - 1, math.ceil((len(residuals) + 1) * .9) - 1)])
            for (i, column), row in model_rows[name].items():
                if column != j:
                    continue
                require(math.isclose(row["mean_t"], means[i] + f["base"][i, j], abs_tol=1e-8), "Historical classical mean replay failed")
                require(math.isclose(row["sd_t"], spreads[i], abs_tol=1e-8), "Historical classical spread replay failed")
                require(math.isclose(row["calibration_multiplier"], calibration, abs_tol=1e-8), "Historical classical calibration population mismatch")
            z = (f["target"][validation, j] - means[validation]) / spreads[validation]
            cdf, pdf = .5 * (1 + erf(z / math.sqrt(2))), np.exp(-z * z / 2) / math.sqrt(2 * math.pi)
            crps = float(np.mean(spreads[validation] * (z * (2 * cdf - 1) + 2 * pdf - 1 / math.sqrt(math.pi))))
            stored = next(r for r in fit["baseline_validation_scores"] if r["model"] == name and r["metric"] == metric)
            require(math.isclose(crps, stored["crps"], abs_tol=1e-9), "Historical baseline selection score mismatch")
        chosen = min((r for r in fit["baseline_validation_scores"] if r["metric"] == metric), key=lambda r: r["crps"])["model"]
        require(chosen == fit["selected_baselines"][metric], "Historical baseline selected on wrong population")
        for (i, column), row in model_rows["hierarchical_damped_2y"].items():
            if column != j:
                continue
            mu, variance = scalar_dynamic(f["raw"][i].reshape(4, 6)[:, j] / f["yscale"][j], dynamic["parameters"], horizon=2)
            require(math.isclose(row["mean_t"], mu * f["yscale"][j], abs_tol=1e-8), "Historical dynamic mean replay failed")
            require(math.isclose(row["sd_t"], math.sqrt(variance) * f["yscale"][j], abs_tol=1e-8), "Historical dynamic covariance replay failed")
    rng = np.random.default_rng(11)
    score_lookup = {(r["model"], r["metric"], r["group"]): r for r in fit["scores"]}
    for metric in OUTCOMES:
        baseline = fit["selected_baselines"][metric]
        names = sorted({r["group"] for r in fit["scores"] if r["metric"] == metric and r["group"].startswith("country:")})
        a = np.array([score_lookup[baseline, metric, name]["crps"] for name in names])
        b = np.array([np.mean([score_lookup[f"network_{seed}", metric, name]["crps"] for seed in (11, 29, 47)]) for name in names])
        n = np.array([score_lookup[baseline, metric, name]["n"] for name in names])
        improvement = float(np.sum((a - b) * n) / np.sum(a * n))
        resamples = rng.integers(0, len(names), (999, len(names)))
        intervals = np.sum((a[resamples] - b[resamples]) * n[resamples], axis=1) / np.sum(a[resamples] * n[resamples], axis=1)
        lower, upper = np.quantile(intervals, [.025, .975])
        stored = next(r for r in fit["learned_comparisons"] if r["metric"] == metric)
        require(stored["validation_selected_baseline"] == baseline and stored["bootstrap_replicates"] == 999, "Historical learned comparison specification changed")
        require(math.isclose(stored["relative_crps_improvement"], improvement, abs_tol=1e-10), "Historical learned comparison mismatch")
        require(math.isclose(stored["cluster_lower"], lower, abs_tol=1e-10) and math.isclose(stored["cluster_upper"], upper, abs_tol=1e-10), "Historical cluster interval mismatch")
        require(stored["practical_5pct_and_positive_interval"] == bool(improvement >= .05 and lower > 0), "Historical practical threshold was relaxed")
    return {**checks, "feature_rows": len(f["keys"]), "prediction_rows": len(predictions), "score_groups": score_groups,
            "configurations": len(model_rows) * 6, "trained_seeds": 3, "exploratory": True}
