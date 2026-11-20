"""Reconstruct forecast splits and scores independently from dated workbook cells."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import mean
from zipfile import ZipFile

import numpy as np
from scipy.stats import beta

from .io import ROOT, contained, digest, read_json
from .verification import require
from .verify_measurement import spreadsheet_cells
from .verify_survey_bridge import compare
from .verify_uk_vintages import column_ref


def released_training(file: Path, edition: dict, config: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    tab = "2018 - "
    with ZipFile(file) as archive:
        values = spreadsheet_cells(archive, {tab})[tab]
    col = column_ref(edition["terminal_column"])
    levels = [(value.split()[1] + value[:2], values.get(col + ref[1:])) for ref, value in values.items()
              if ref.startswith("A") and ref[1:].isdigit() and isinstance(value, str)
              and len(value) == 7 and value.startswith(("Q1 ", "Q2 ", "Q3 ", "Q4 "))]
    selected = [(q, level) for q, level in levels if "1999Q4" <= q <= config["validation_end"]]
    require(all(isinstance(v, float) and v > 0 for _, v in selected), "GDP training workbook time series differs")
    quarters, raw = zip(*selected, strict=True)
    require(quarters[0] == "1999Q4" and quarters[-1] == config["validation_end"] and len(quarters) == 88,
            "GDP training historical reference range differs")
    raw = np.array(raw)
    growth = np.diff(raw) * 100 / raw[:-1]
    sliding = np.lib.stride_tricks.sliding_window_view(growth, 5)
    targets = np.array(quarters[5:])
    training = sliding[(targets >= config["training_start"]) & (targets <= config["training_end"])]
    validation = sliding[(targets >= config["validation_start"]) & (targets <= config["validation_end"])]
    require(len(training) == 72 and len(validation) == 11, "GDP forecast fitting split changed")
    center = training[:, :4].mean(axis=0)
    scale = np.sqrt(np.mean((training[:, :4] - center) ** 2, axis=0))
    scales = np.maximum(scale, .0001)
    design = np.column_stack((np.ones(len(training)), (training[:, :4] - center) / scales))
    penalties = np.column_stack((np.zeros(4), np.eye(4)))
    coefficients = {}
    for strength in config["ridge_penalties"]:
        augmented_x = np.concatenate((design, penalties * np.sqrt(strength)), axis=0)
        augmented_y = np.append(training[:, 4], np.zeros(4))
        coefficients[f"ridge_{strength}"] = np.linalg.lstsq(augmented_x, augmented_y, rcond=None)[0]
    forecast = forecast_matrix(validation[:, :4], center, scales, coefficients)
    validation_losses = {model: float(np.abs(p - validation[:, -1]).mean()) for model, p in forecast.items()}
    selected_fixed = sorted(config["baseline_models"], key=lambda m: (validation_losses[m], m))[0]
    selected_ridge = sorted(coefficients, key=lambda m: (validation_losses[m], m))[0]
    return center, scales, {
        "training_rows": len(training), "validation_rows": len(validation), "validation_mae": validation_losses,
        "selected_baseline": selected_fixed, "selected_ridge": selected_ridge,
        "ridge_parameters": coefficients,
    }


def forecast_matrix(features: np.ndarray, center: np.ndarray, scale: np.ndarray, coeff: dict) -> dict:
    return {
        "zero": np.zeros(len(features)), "persistence": features[:, 3], "rolling_mean": features.mean(axis=1),
        "seasonal_naive": features[:, 0],
        **{m: parameters[0] + ((features - center) / scale) @ parameters[1:] for m, parameters in coeff.items()},
    }


def verify_uk_forecast(bundle: Path, raw: Path, source: str) -> dict:
    definition = ROOT / "configs/uk-forecast-v9.json"
    cfg = read_json(definition)
    upstream = bundle / "uk-vintages.json"
    data = read_json(bundle / "uk-forecast.json")
    editions = read_json(upstream)["editions"]
    require(data["source"] == source and data["schema_version"] == 1
            and data["target"] == cfg["target"] and data["scope"] == cfg["scope"]
            and data["config_sha256"] == digest(definition)
            and data["vintages_sha256"] == digest(upstream), "GDP forecast provenance differs")
    manifest = read_json(ROOT / "configs/uk-vintages-inputs.json")
    fit_release = next(row for row in manifest["editions"] if row["workbook"]["id"] == cfg["initial_release_id"])
    file = contained(raw, fit_release["workbook"]["path"])
    require(data["fit_release"] == fit_release["release_day"]
            and data["fit_workbook_sha256"] == digest(file) == fit_release["workbook"]["sha256"],
            "GDP forecast initial workbook source differs")
    center, scale, fitted = released_training(file, fit_release, cfg)
    development = data["development"]
    require(development["training_rows"] == fitted["training_rows"] and development["validation_rows"] == fitted["validation_rows"]
            and development["selected_baseline"] == fitted["selected_baseline"]
            and development["selected_ridge"] == fitted["selected_ridge"], "GDP forecast validation selection differs")
    for key, values in (("lag_center", center), ("lag_scale", scale)):
        require(len(development[key]) == 4 and np.allclose(development[key], values, atol=1e-10, rtol=1e-10),
                "GDP forecast lag preprocessing differs")
    coeff = fitted["ridge_parameters"]
    require(set(development["ridge_parameters"]) == set(coeff), "GDP forecast penalty inventory differs")
    for key, params in coeff.items():
        require(len(development["ridge_parameters"][key]) == 5
                and np.allclose(development["ridge_parameters"][key], params, atol=1e-10, rtol=1e-10),
                "GDP forecast ridge coefficients differ")
    compare(development["validation_mae"], fitted["validation_mae"], "GDP validation losses")

    estimation = [r for r in editions if r["kind"] == "first"]
    quarterly = [r for r in editions if r["kind"] == "qna"]
    require([r["quarter"] for r in estimation] == [r["quarter"] for r in quarterly], "GDP source edition population differs")
    require(len(data["origins"]) == len(estimation) - 1, "GDP forecast evaluated quarter population differs")
    residuals = defaultdict(list)
    expected = {}
    for item, initial, revised, previous in zip(data["origins"], estimation[1:], quarterly[1:], quarterly[:-1], strict=True):
        quarter = initial["quarter"]
        role = "calibration" if cfg["calibration_start"] <= quarter <= cfg["calibration_end"] else "test"
        require(previous["release_day"] < initial["release_day"] < revised["release_day"]
                and (role == "calibration" or cfg["evaluation_start"] <= quarter <= cfg["evaluation_end"]),
                "GDP prediction target or origin chronology invalid")
        lags = previous["observations"][-4:]
        guesses = forecast_matrix(np.array([[x["growth_pct"] for x in lags]]), center, scale, coeff)
        estimates = {m: float(v[0]) for m, v in guesses.items()}
        expect = {
            "quarter": quarter, "role": role, "origin": previous["release_day"],
            "origin_workbook_sha256": previous["workbook_sha256"], "origin_release_id": previous["release_id"],
            "first_release": initial["release_day"], "qna_release": revised["release_day"],
            "first_growth_pct": initial["observations"][-1]["growth_pct"],
            "qna_growth_pct": revised["observations"][-1]["growth_pct"],
            "lag_quarters": [x["quarter"] for x in lags], "growth_lags": [x["growth_pct"] for x in lags],
        }
        compare({k: v for k, v in item.items() if k != "model_points"}, expect, "GDP forecast origins and lags")
        compare(item["model_points"], estimates, "GDP archive-based forecast")
        for model, point in estimates.items():
            if role == "calibration":
                residuals[model].append(abs(expect["first_growth_pct"] - point))
            else:
                expected[quarter, model] = (expect, point)

    given = {(row["quarter"], row["model"]): row for row in data["predictions"]}
    require(set(given) == set(expected) and len(given) == len(data["predictions"]), "GDP test forecast rows changed")
    require(set(residuals) == set(data["scores"]), "GDP model scores omitted")
    for model, errors in residuals.items():
        require(len(errors) == 9, "GDP calibration population differs")
        rounded_up_rank = int(np.ceil(10 * cfg["nominal_coverage"]))
        radius = float(np.partition(errors, rounded_up_rank - 1)[rounded_up_rank - 1])
        absolute_errors, interval_scores = [], []
        coverage = revision_coverage = 0
        for (q, m), (release, point) in expected.items():
            if m != model:
                continue
            y, revised = release["first_growth_pct"], release["qna_growth_pct"]
            low, high = point - radius, point + radius
            distance = max(low - y, y - high, 0.)
            alpha = 1 - cfg["nominal_coverage"]
            score = 2 * radius + distance / (alpha / 2)
            included, revised_included = low <= y <= high, low <= revised <= high
            coverage += included
            revision_coverage += revised_included
            absolute_errors.append(abs(y - point))
            interval_scores.append(score)
            compare(given[q, m], {"quarter": q, "model": m, "forecast_pct": point, "lower": low,
                                   "upper": high, "first_growth_pct": y, "qna_growth_pct": revised,
                                   "covered": included, "revised_covered": revised_included, "interval_score": score,
                                   "origin": release["origin"], "first_release": release["first_release"]}, "GDP held-out interval")
        n = len(interval_scores)
        require(n == 8, "GDP test cohort length differs")
        estimate = data["scores"][model]
        require(len(estimate["calibration_absolute_errors_pp"]) == len(errors) and np.allclose(
            estimate["calibration_absolute_errors_pp"], sorted(errors), atol=1e-10, rtol=1e-10
        ), "GDP calibration residuals were substituted")
        compare({k: v for k, v in estimate.items() if k != "calibration_absolute_errors_pp"}, {
            "calibration_n": len(errors), "calibration_rank": rounded_up_rank, "radius_pp": radius, "n": n,
            "covered": coverage, "coverage": coverage / n, "coverage_lower": float(beta.ppf(.025, coverage, n - coverage + 1)) if coverage else 0.,
            "coverage_upper": float(beta.ppf(.975, coverage + 1, n - coverage)) if coverage < n else 1.,
            "revised_covered": revision_coverage, "mae_pp": mean(absolute_errors), "mean_interval_score": mean(interval_scores),
            "interval_width_pp": 2 * radius, "practical_coverage_met": coverage >= cfg["practical_minimum_covered"],
        }, "GDP held-out coverage and interval score")
    return {"models": len(residuals), "quarters": 8, "prediction_checks": len(expected),
            "validation_selected_baseline": fitted["selected_baseline"],
            "validation_selected_ridge": fitted["selected_ridge"]}
