"""Score registered GDP growth forecasts using exact archived release origins."""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import binomtest

from .io import ROOT, digest, read_json, source_commit, write_json
from .uk_vintages import DEFINITION, PINS, RESULT as VINTAGES, archive_values, checked

CONFIG = ROOT / "configs/uk-forecast-v9.json"
RESULT = ROOT / "data/results/uk-forecast.json"


def period_index(quarter: str) -> int:
    return int(quarter[:4]) * 4 + int(quarter[-1]) - 1


def quarter_label(index: int) -> str:
    return f"{index // 4}Q{index % 4 + 1}"


def baseline_values(lags: np.ndarray) -> dict:
    return {"zero": 0., "persistence": float(lags[-1]), "rolling_mean": float(np.mean(lags)),
            "seasonal_naive": float(lags[0])}


def prediction(lags: np.ndarray, coefficients: dict, center: np.ndarray, scale: np.ndarray) -> dict:
    x = np.concatenate(([1.], (lags - center) / scale))
    return {**baseline_values(lags), **{name: float(x @ beta) for name, beta in coefficients.items()}}


def fit_rules(points: dict[str, float], config: dict) -> tuple:
    eligible = range(period_index(config["training_start"]), period_index(config["validation_end"]) + 1)
    samples = [
        (quarter_label(index), np.array([points[quarter_label(i)] for i in range(index - 4, index)]),
         points[quarter_label(index)])
        for index in eligible
    ]
    trained = [row for row in samples if row[0] <= config["training_end"]]
    validation = [row for row in samples if config["validation_start"] <= row[0] <= config["validation_end"]]
    x, y = np.vstack([row[1] for row in trained]), np.array([row[2] for row in trained])
    center, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-4)
    design = np.column_stack((np.ones(len(x)), (x - center) / scale))
    coefficients = {}
    for penalty in config["ridge_penalties"]:
        regularizer = np.eye(design.shape[1]) * penalty
        regularizer[0, 0] = 0
        coefficients[f"ridge_{penalty}"] = np.linalg.solve(design.T @ design + regularizer, design.T @ y)
    errors: dict[str, list[float]] = {}
    for _, feature, target in validation:
        for model, forecast in prediction(feature, coefficients, center, scale).items():
            errors.setdefault(model, []).append(abs(target - forecast))
    summary = {model: float(np.mean(values)) for model, values in errors.items()}
    best_baseline = min(config["baseline_models"], key=lambda name: (summary[name], name))
    best_ridge = min(coefficients, key=lambda name: (summary[name], name))
    return coefficients, center, scale, {
        "training_rows": len(trained), "validation_rows": len(validation),
        "validation_mae": summary, "selected_baseline": best_baseline, "selected_ridge": best_ridge,
        "lag_center": center.tolist(), "lag_scale": scale.tolist(),
        "ridge_parameters": {name: values.tolist() for name, values in coefficients.items()},
    }


def interval_scores(rows: list[dict], config: dict) -> tuple[dict, list[dict]]:
    alpha = 1 - config["nominal_coverage"]
    calibration = [r for r in rows if r["role"] == "calibration"]
    test = [r for r in rows if r["role"] == "test"]
    bound_rank = math.ceil((len(calibration) + 1) * config["nominal_coverage"])
    if len(test) != 8 or len(calibration) != 9 or bound_rank > len(calibration):
        raise ValueError("GDP release calibration or test cohort differs from the registered schedule")
    scores, predictions = {}, []
    for model in rows[0]["model_points"]:
        errors = sorted(abs(row["first_growth_pct"] - row["model_points"][model]) for row in calibration)
        radius = errors[bound_rank - 1]
        losses, scores_by_row, covered, revised_covered = [], [], 0, 0
        for row in test:
            point = row["model_points"][model]
            observed = row["first_growth_pct"]
            low, high = point - radius, point + radius
            under, over = max(0., low - observed), max(0., observed - high)
            losses.append(abs(observed - point))
            score = high - low + 2 / alpha * (under + over)
            scores_by_row.append(score)
            match = low <= observed <= high
            match_revised = low <= row["qna_growth_pct"] <= high
            covered += match
            revised_covered += match_revised
            predictions.append({"quarter": row["quarter"], "model": model, "forecast_pct": point, "lower": low,
                                "upper": high, "first_growth_pct": observed, "qna_growth_pct": row["qna_growth_pct"],
                                "covered": match, "revised_covered": match_revised, "interval_score": score,
                                "origin": row["origin"], "first_release": row["first_release"]})
        interval = binomtest(covered, len(test)).proportion_ci(confidence_level=.95, method="exact")
        scores[model] = {
            "calibration_n": len(calibration), "calibration_rank": bound_rank, "radius_pp": radius,
            "calibration_absolute_errors_pp": errors, "n": len(test), "covered": covered,
            "coverage": covered / len(test), "coverage_lower": float(interval.low), "coverage_upper": float(interval.high),
            "revised_covered": revised_covered, "mae_pp": float(np.mean(losses)),
            "mean_interval_score": float(np.mean(scores_by_row)), "interval_width_pp": 2 * radius,
            "practical_coverage_met": covered >= config["practical_minimum_covered"],
        }
    return scores, predictions


def build_uk_forecast() -> dict:
    config, manifest, chronology = map(read_json, (CONFIG, PINS, VINTAGES))
    if chronology["source"] != source_commit():
        raise ValueError("Recompute date-frozen GDP vintage features before forecasting")
    initial = next(row for row in manifest["editions"] if row["workbook"]["id"] == config["initial_release_id"])
    training_def = {**read_json(DEFINITION), "first_reference_quarter": "2000Q1"}
    known = archive_values(checked(initial["workbook"]), initial, training_def)
    coefficients, center, scale, fitted = fit_rules({r["quarter"]: r["growth_pct"] for r in known}, config)
    editions = {(r["quarter"], r["kind"]): r for r in chronology["editions"]}
    staged = []
    for revision in chronology["revisions"]:
        quarter = revision["quarter"]
        if quarter < config["calibration_start"] or quarter > config["evaluation_end"]:
            continue
        preceding = quarter_label(period_index(quarter) - 1)
        origin = editions[preceding, "qna"]
        if not initial["release_day"] <= origin["release_day"] < revision["first_release"]:
            raise ValueError("A GDP forecast would use a source outside its valid release origin")
        lags = origin["observations"][-4:]
        if [q["quarter"] for q in lags] != [
            quarter_label(i) for i in range(period_index(quarter) - 4, period_index(quarter))
        ]:
            raise ValueError("Forecast lags do not end in the immediately prior reference quarter")
        staged.append({
            "quarter": quarter, "role": "calibration" if quarter <= config["calibration_end"] else "test",
            "origin": origin["release_day"], "origin_workbook_sha256": origin["workbook_sha256"],
            "origin_release_id": origin["release_id"], "first_release": revision["first_release"],
            "qna_release": revision["qna_release"], "first_growth_pct": revision["first_growth_pct"],
            "qna_growth_pct": revision["qna_growth_pct"],
            "lag_quarters": [r["quarter"] for r in lags], "growth_lags": [r["growth_pct"] for r in lags],
            "model_points": prediction(np.array([r["growth_pct"] for r in lags]), coefficients, center, scale),
        })
    scores, predictions = interval_scores(staged, config)
    data = {
        "schema_version": 1, "source": source_commit(), "target": config["target"], "scope": config["scope"],
        "config_sha256": digest(CONFIG), "vintages_sha256": digest(VINTAGES), "fit_release": initial["release_day"],
        "fit_workbook_sha256": initial["workbook"]["sha256"], "development": fitted, "origins": staged,
        "scores": scores, "predictions": predictions,
    }
    write_json(RESULT, data)
    return data
