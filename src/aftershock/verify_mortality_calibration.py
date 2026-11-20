"""Reconstruct dated mortality cohorts, fixed predictors and uncertainty independently."""
from __future__ import annotations

import csv
import hashlib
import io
import math
from statistics import mean

import numpy as np

from .io import ROOT, digest, read_json
from .mortality_calibration import source_bytes
from .verification import require
from .verify_survey_bridge import compare


def table(raw: bytes, coverage: set[str], years: set[int]) -> dict:
    stream = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    fields = next(stream)
    required = [fields.index(k) for k in ("country_name", "year", "time", "time_unit", "deaths")]
    lookup = {}
    for record in stream:
        area, year, week, frequency, count = (record[i] for i in required)
        if area not in coverage or frequency != "weekly" or int(year) not in years or not 1 <= int(week) <= 52:
            continue
        key = area, int(year), int(week)
        require(key not in lookup and math.isfinite(float(count)) and float(count) >= 0, "Raw mortality count identity differs")
        lookup[key] = float(count)
    return {(area, year): np.array([lookup[area, year, w] for w in range(1, 53)])
            for area in coverage for year in years if all((area, year, week) in lookup for week in range(1, 53))}


def wave_vector(year: int) -> np.ndarray:
    basis = []
    for week in range(1, 53):
        angle = (week - .5) * math.tau / 52
        basis.append([1, year - 2015, *(f(j * angle) for j in (1, 2, 3) for f in (math.sin, math.cos))])
    return np.asarray(basis)


def forecasts(year: int, local: np.ndarray, area_scale: float, weights: dict) -> dict:
    quarterly = local.sum(axis=1) / 52
    centered = np.arange(4) - 1.5
    slope = (quarterly @ centered) / (centered @ centered)
    adjustment = quarterly[-1] - np.mean(quarterly) + slope * (1 - .5 ** (year - 2018))
    local_mean = local.sum(axis=0) / 4
    return {"seasonal_persistence": local[3] / area_scale, "seasonal_mean": local_mean / area_scale,
            "damped_trend": np.clip(local_mean + adjustment, 1, None) / area_scale,
            **{key: np.clip(wave_vector(year) @ value, 1 / area_scale, None) for key, value in weights.items()}}


def held_out(area: str) -> bool:
    marker = hashlib.sha256(area.encode()).digest()
    return int.from_bytes(marker, "big") % 5 == 0


def reconstruct(config: dict) -> tuple:
    raw = {}
    for name, years in {
        "features": set(range(2015, 2020)), "calibration": {2022}, "evaluation": {2024}, "revision": {2024}
    }.items():
        raw[name] = table(source_bytes(config["sources"][name]), set(config["countries"]), years)
    development, scales, missing = {}, {}, []
    for area in config["countries"]:
        if all((area, year) in raw["features"] for year in range(2015, 2020)) and raw["features"][area, 2015].sum() > 0:
            development[area] = np.vstack([raw["features"][area, year] for year in range(2015, 2019)])
            scales[area] = float(raw["features"][area, 2015].sum() / 52)
        else:
            missing.append(area)
    fit = [a for a in development if not held_out(a)]
    calibration = [a for a in fit if (a, 2022) in raw["calibration"]]
    evaluation = [a for a in development if (a, 2024) in raw["evaluation"]]
    holdout = [a for a in evaluation if held_out(a)]
    outcomes_missing = {
        area: [mode for mode, year in (("calibration", 2022), ("evaluation", 2024), ("revision", 2024))
               if (area, year) not in raw[mode]]
        for area in config["countries"]
    }
    return raw, development, scales, {
        "fit": fit, "calibration": calibration, "test": evaluation, "held_out": holdout,
        "missing_development": missing, "missing_outcomes": outcomes_missing,
    }


def compare_scores(scores: list[dict], models: list[str], cohort: dict, rows: dict, config: dict) -> int:
    test = cohort["test"]
    definitions = {"all": test, "held_out": cohort["held_out"], **{a: [a] for a in test}}
    keys = {(row["model"], row["group"]): row for row in scores}
    require(set(keys) == {(model, key) for model in models for key in definitions}
            and len(keys) == len(scores), "Mortality score cohort is incomplete")
    for model in models:
        for name, areas in definitions.items():
            population = [rows[model, area, w] for area in areas for w in range(1, 53)]
            per_area = [sum(row["covered"] for row in population if row["region"] == area) / 52 for area in areas]
            instances = np.random.default_rng(config["bootstrap_seed"]).integers(
                0, len(areas), size=(config["bootstrap_draws"], len(areas)))
            boot = [mean(per_area[j] for j in draw) for draw in instances.tolist()]
            lower, upper = np.quantile(boot, [0.025, .975])
            inside = float(mean(per_area))
            revision = [row["revision_covered"] for row in population if row["revision_covered"] is not None]
            lo, hi = config["practical_coverage_range"]
            want = {"model": model, "group": name, "countries": len(areas), "weeks": len(population),
                    "coverage": inside, "coverage_cluster_lower": float(lower), "coverage_cluster_upper": float(upper),
                    "practical_coverage_met": lo <= inside <= hi, "revision_weeks": len(revision),
                    "revision_coverage": float(mean(revision)) if revision else None,
                    "mean_absolute_error_normalized": float(mean(r["absolute_error"] for r in population)),
                    "mean_interval_score_normalized": float(mean(r["interval_score"] for r in population)),
                    "mean_width_normalized": float(mean(r["standardized_upper"] - r["standardized_lower"] for r in population))}
            compare(keys[model, name], want, "mortality country-bootstrap and held-out scores")
    return len(keys)


def verify_mortality(data: dict, source: str) -> dict:
    file = ROOT / "configs/mortality-calibration-v11.json"
    cfg = read_json(file)
    pins = cfg["sources"]
    require(data["source"] == source and data["schema_version"] == 1 and data["definition_sha256"] == digest(file)
            and data["origins"] == cfg["origins"] and data["upstream"] == pins
            and data["source_citation"] == cfg["source_citation"] and data["source_rights"] == cfg["source_rights"],
            "Mortality forecast availability or source changed")
    require(pins["features"]["provider_snapshot_at"] < cfg["origins"]["calibration"]
            and "2022-12-31" < pins["calibration"]["provider_snapshot_at"] < cfg["origins"]["evaluation"]
            and "2024-12-31" < pins["evaluation"]["provider_snapshot_at"] < pins["revision"]["provider_snapshot_at"],
            "Mortality forecast uses a future archive by role")
    raw, dev, scales, cohort = reconstruct(cfg)
    require(data["cohorts"] == cohort, "Mortality geographic holdout or completeness changed")
    compare(data["scales"], scales, "mortality baseline scales")
    require(not set(cohort["held_out"]) & (set(cohort["fit"]) | set(cohort["calibration"])),
            "Mortality holdout leaked into training or calibration")

    design = np.vstack([wave_vector(y) for y in (2016, 2017, 2018)] * len(cohort["fit"]))
    target = np.array([observation / scales[area] for area in cohort["fit"]
                       for year in (2016, 2017, 2018) for observation in raw["features"][area, year]])
    strength = np.column_stack((np.zeros(7), np.eye(7)))
    fitted = {}
    for penalty in cfg["ridge_penalties"]:
        model = f"ridge_{penalty:g}"
        extra = strength * math.sqrt(penalty)
        beta = np.linalg.lstsq(np.vstack((design, extra)), np.concatenate((target, np.zeros(7))), rcond=None)[0]
        estimate = data["trained_coefficients"][model]
        require(len(estimate) == 8 and np.allclose(estimate, beta, rtol=1e-8, atol=1e-8),
                "Mortality trained weights differ from the registered split")
        fitted[model] = beta
    require(set(fitted) == set(data["trained_coefficients"]), "Mortality trained penalty inventory differs")
    validation_errors: dict[str, list[float]] = {}
    for area in cohort["fit"]:
        valid = raw["features"][area, 2019] / scales[area]
        for model, estimate in forecasts(2019, dev[area], scales[area], fitted).items():
            validation_errors.setdefault(model, []).extend(np.abs(valid - estimate).tolist())
    errors = {m: float(mean(values)) for m, values in validation_errors.items()}
    want_baseline = min((m for m in errors if m not in fitted), key=lambda m: (errors[m], m))
    want_ridge = min(fitted, key=lambda m: (errors[m], m))
    require(data["validation"]["selected_baseline"] == want_baseline and data["validation"]["selected_ridge"] == want_ridge,
            "Mortality validation-selected models differ")
    compare(data["validation"]["normalized_mae"], errors, "mortality validation losses")

    radii = {}
    records = {row["model"]: row for row in data["calibrations"]}
    require(set(records) == set(errors) and len(records) == len(data["calibrations"]), "Mortality calibration inventory differs")
    for model in errors:
        deviations = []
        for area in cohort["calibration"]:
            y = raw["calibration"][area, 2022] / scales[area]
            prior = forecasts(2022, dev[area], scales[area], fitted)[model]
            deviations.extend(np.abs(y - prior).tolist())
        n = len(deviations)
        k = math.ceil(cfg["coverage_level"] * (n + 1))
        radius = sorted(deviations)[k - 1]
        compare(records[model], {"model":model,"radius_normalized":radius,"rank":k,"calibration_rows":n},
                "mortality calibrated radius")
        radii[model] = radius

    predicted = {(r["model"], r["region"], r["week"]): r for r in data["predictions"]}
    expected_size = len(cohort["test"]) * 52 * len(radii)
    require(len(predicted) == len(data["predictions"]) == expected_size, "Mortality forecast rows omitted or duplicated")
    for area in cohort["test"]:
        count = raw["evaluation"][area, 2024] / scales[area]
        revised = raw["revision"].get((area, 2024))
        for model, expected in forecasts(2024, dev[area], scales[area], fitted).items():
            for i in range(52):
                value, point, r = float(count[i]), float(expected[i]), radii[model]
                y2 = float(revised[i] / scales[area]) if revised is not None else None
                a, b = max(0., point - r), point + r
                error = (a - value if value < a else value - b if value > b else 0.)
                row = {"region":area,"week":i+1,"model":model,"standardized_forecast":point,
                       "standardized_lower":a,"standardized_upper":b,"standardized_observed":value,
                       "standardized_revision":y2,"covered":a<=value<=b,"revision_covered":a<=y2<=b if y2 is not None else None,
                       "absolute_error":abs(point-value),"interval_score":b-a+2/(1-cfg["coverage_level"])*error}
                compare(predicted[model, area, i + 1], row, "mortality evaluation prediction or coverage")
    checks = compare_scores(data["scores"], list(errors), cohort, predicted, cfg)
    final = {(r["model"], r["group"]): r for r in data["scores"]}
    return {"test_rows": expected_size, "score_checks": checks, "test_countries": len(cohort["test"]),
            "held_out_countries": len(cohort["held_out"]), "evaluation_weeks": len(cohort["test"]) * 52,
            "selected_ridge": want_ridge, "selected_baseline": want_baseline,
            "ridge_passes_observed_coverage": all(final[want_ridge, g]["practical_coverage_met"] for g in ("all", "held_out"))}
