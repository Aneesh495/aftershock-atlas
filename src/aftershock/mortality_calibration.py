"""Train and evaluate weekly mortality forecasts on dated public aggregates."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import subprocess

import numpy as np

from .features import held_out
from .io import ROOT, digest, read_json, source_commit, write_json

CONFIG = ROOT / "configs/mortality-calibration-v11.json"
RESULT = ROOT / "data/results/mortality-calibration.json"
BASELINES = ("seasonal_persistence", "seasonal_mean", "damped_trend")
WEEKS = np.arange(1, 53)


def source_bytes(pin: dict) -> bytes:
    url = f'https://raw.githubusercontent.com/akarlinsky/world_mortality/{pin["commit"]}/world_mortality.csv'
    if pin["url"] != url or len(pin["commit"]) != 40:
        raise ValueError("Mortality archive must use a pinned GitHub data commit")
    proc = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
         "--proto-redir", "=https", "--max-time", "30", "--max-filesize", "1800000", url],
        check=True, capture_output=True, timeout=35,
    )
    raw = proc.stdout
    if len(raw) != pin["bytes"] or hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("Mortality archive bytes differ from the registered snapshot")
    return raw


def load_series(raw: bytes, countries: set[str], years: set[int]) -> dict:
    result = {}
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    accepted = {"country_name", "year", "time", "time_unit", "deaths"}
    if set(reader.fieldnames or ()) not in (accepted, accepted | {"iso3c"}):
        raise ValueError("Mortality archive field inventory changed")
    for row in reader:
        country = row["country_name"]
        year, week = int(row["year"]), int(row["time"])
        if country not in countries or year not in years or row["time_unit"] != "weekly" or not 1 <= week <= 52:
            continue
        y = float(row["deaths"])
        if not math.isfinite(y) or y < 0:
            raise ValueError("Mortality count cannot be negative or nonfinite")
        key = (country, year, week)
        if key in result:
            raise ValueError("Duplicated mortality week under a country identity")
        result[key] = y
    return result


def complete(series: dict, region: str, year: int) -> np.ndarray | None:
    data = [series.get((region, year, week)) for week in WEEKS]
    return np.array(data, dtype=float) if all(value is not None for value in data) else None


def design(year: int) -> np.ndarray:
    time = np.full(52, year - 2015, dtype=float)
    theta = (WEEKS - .5) * 2 * np.pi / 52
    return np.column_stack((np.ones(52), time, *(fn(theta * shift)
        for shift in (1, 2, 3) for fn in (np.sin, np.cos))))


def center(year: int, known: np.ndarray, scale: float, coefficients: dict) -> dict[str, np.ndarray]:
    season = known.mean(axis=0)
    national = known.mean(axis=1)
    slope = float(np.polyfit(np.arange(len(national)), national, 1)[0])
    damping = sum(.5 ** step for step in range(1, year - 2018 + 1))
    expected = {"seasonal_persistence": known[-1], "seasonal_mean": season,
                "damped_trend": np.maximum(season + (national[-1] - national.mean()) + damping * slope, 1)}
    for model, params in coefficients.items():
        expected[model] = np.maximum(scale * (design(year) @ params), 1)
    return expected


def train_models(development: dict, scales: dict, eligible: list[str], config: dict) -> tuple[dict, dict]:
    periods = config["train_years"]
    x = np.vstack([design(year) for _ in eligible for year in periods])
    y = np.concatenate([development[region][offset + 1] / scales[region]
                        for region in eligible for offset in range(len(periods))])
    strength = np.eye(x.shape[1])
    strength[0, 0] = 0
    coefficients = {}
    for penalty in config["ridge_penalties"]:
        coefficients[f"ridge_{penalty:g}"] = np.linalg.solve(x.T @ x + penalty * strength, x.T @ y)
    return coefficients, {k: v.tolist() for k, v in coefficients.items()}


def role_archive(pins: dict, config: dict) -> dict:
    feature_day, calibration_day, evaluation_day, revision_day = (
        pins[role]["provider_snapshot_at"][:10] for role in ("features", "calibration", "evaluation", "revision")
    )
    if not (feature_day < config["origins"]["calibration"]
            and f'{config["calibration_year"]}-12-31' < calibration_day < config["origins"]["evaluation"]
            and f'{config["evaluation_year"]}-12-31' < evaluation_day < revision_day):
        raise ValueError("Mortality outcome archive is outside the registered forecast roles")
    selection = set(config["countries"])
    sources = {
        "features": {config["scale_year"], *config["train_years"], config["validation_year"]},
        "calibration": {config["calibration_year"]}, "evaluation": {config["evaluation_year"]},
        "revision": {config["evaluation_year"]},
    }
    return {role: load_series(source_bytes(pins[role]), selection, year) for role, year in sources.items()}


def compare_forecasts(data: dict, truth: dict, design_cohorts: dict, config: dict) -> tuple[list[dict], list[dict], dict]:
    validation_year = config["validation_year"]
    validation = {}
    forecasts_calibration, forecast_test = {}, {}
    roles = ("development", "calibration", "evaluation")
    for role in roles:
        if role == "development":
            eligible = design_cohorts["fit"]
            for model, points in data[validation_year].items():
                validation[model] = float(np.mean([np.abs(points[area] - truth[role][area]).mean()
                                                  for area in eligible]))
        else:
            annual = config["calibration_year" if role == "calibration" else "evaluation_year"]
            choice = forecasts_calibration if role == "calibration" else forecast_test
            choice.update(data[annual])
    baseline = min(BASELINES, key=lambda model: (validation[model], model))
    ridge = min((model for model in validation if model.startswith("ridge_")), key=lambda model: (validation[model], model))
    posterior, errors = [], []
    calib_areas = design_cohorts["calibration"]
    probability = config["coverage_level"]
    alpha = 1 - probability
    for model, points in forecast_test.items():
        residuals = np.concatenate([np.abs(forecasts_calibration[model][r] - truth["calibration"][r]) for r in calib_areas])
        n = int(residuals.size)
        rank = math.ceil((n + 1) * probability)
        if not 1 <= rank <= n:
            raise ValueError("Mortality calibration cohort cannot identify the requested quantile")
        radius = float(np.partition(residuals, rank - 1)[rank - 1])
        errors.append({"model": model, "radius_normalized": radius, "calibration_rows": n, "rank": rank})
        for area in design_cohorts["test"]:
            point = points[area]
            y = truth["evaluation"][area]
            revised = truth["revision"].get(area)
            for index, (guess, outcome) in enumerate(zip(point, y, strict=True)):
                low, high = max(0., guess - radius), guess + radius
                cover = low <= outcome <= high
                revised_y = float(revised[index]) if revised is not None else None
                posterior.append({
                    "region": area, "week": index + 1, "model": model, "standardized_forecast": float(guess),
                    "standardized_lower": float(low), "standardized_upper": float(high), "standardized_observed": float(outcome),
                    "standardized_revision": revised_y, "covered": bool(cover),
                    "revision_covered": bool(low <= revised_y <= high) if revised_y is not None else None,
                    "absolute_error": float(abs(guess - outcome)),
                    "interval_score": float(high - low + (2 / alpha) * max(low - outcome, outcome - high, 0.)),
                })
    return errors, posterior, {"normalized_mae": validation, "selected_baseline": baseline, "selected_ridge": ridge}


def score(rows: list[dict], groups: dict, config: dict) -> list[dict]:
    selected = sorted({row["model"] for row in rows})
    floor, ceiling = config["practical_coverage_range"]
    result = []
    for model in selected:
        found = [row for row in rows if row["model"] == model]
        for group, regions in {"all": groups["test"], "held_out": groups["held_out"], **{
            region: [region] for region in groups["test"]
        }}.items():
            users = [row for row in found if row["region"] in regions]
            per_region = np.asarray([np.mean([row["covered"] for row in users if row["region"] == region])
                                     for region in regions])
            rng = np.random.default_rng(config["bootstrap_seed"])
            picks = rng.integers(0, len(regions), size=(config["bootstrap_draws"], len(regions)))
            lower, upper = np.quantile(per_region[picks].mean(axis=1), [.025, .975])
            c = float(per_region.mean())
            with_revision = [row["revision_covered"] for row in users if row["revision_covered"] is not None]
            result.append({
                "model": model, "group": group, "countries": len(regions), "weeks": len(users), "coverage": c,
                "coverage_cluster_lower": float(lower), "coverage_cluster_upper": float(upper),
                "practical_coverage_met": floor <= c <= ceiling, "revision_weeks": len(with_revision),
                "revision_coverage": float(np.mean(with_revision)) if with_revision else None,
                "mean_absolute_error_normalized": float(np.mean([row["absolute_error"] for row in users])),
                "mean_interval_score_normalized": float(np.mean([row["interval_score"] for row in users])),
                "mean_width_normalized": float(np.mean([row["standardized_upper"] - row["standardized_lower"] for row in users])),
            })
    return result


def build_mortality_calibration() -> dict:
    config = read_json(CONFIG)
    pins = config["sources"]
    raw = role_archive(pins, config)
    design_years = [config["scale_year"], *config["train_years"]]
    archive = {}
    omissions = []
    missing = {}
    for region in config["countries"]:
        known = [complete(raw["features"], region, year) for year in design_years]
        latest = complete(raw["features"], region, config["validation_year"])
        result = {role: complete(raw[role], region, config["calibration_year" if role == "calibration" else "evaluation_year"])
                  for role in ("calibration", "evaluation", "revision")}
        missing[region] = [role for role, value in result.items() if value is None]
        if any(item is None for item in known) or latest is None or known[0].mean() <= 0:
            omissions.append(region)
            continue
        archive[region] = (np.vstack(known), latest, result)
    scales = {region: float(values[0][0].mean()) for region, values in archive.items()}
    training = [region for region in archive if not held_out(region)]
    calibration = [region for region in training if archive[region][2]["calibration"] is not None]
    test = [region for region in archive if archive[region][2]["evaluation"] is not None]
    holdout = [region for region in test if held_out(region)]
    if len(calibration) < 10 or len(holdout) < 3 or len(test) < 15:
        raise ValueError("Mortality archive cannot support the registered region and time comparisons")
    cohorts = {"fit": training, "calibration": calibration, "test": test, "held_out": holdout,
               "missing_development": omissions, "missing_outcomes": missing}
    coefficients, trained = train_models({r: v[0] for r, v in archive.items()}, scales, training, config)
    model_data = {}
    for year in (config["validation_year"], config["calibration_year"], config["evaluation_year"]):
        forecasts = {model: {} for model in (*BASELINES, *coefficients)}
        for region, (history, _, _) in archive.items():
            for name, vector in center(year, history, scales[region], coefficients).items():
                forecasts[name][region] = vector / scales[region]
        model_data[year] = forecasts
    truth = {role: {} for role in ("development", "calibration", "evaluation", "revision")}
    for region, (_, valid, trial) in archive.items():
        truth["development"][region] = valid / scales[region]
        for role, value in trial.items():
            if value is not None:
                truth[role][region] = value / scales[region]
    radii, predictions, choice = compare_forecasts(model_data, truth, cohorts, config)
    data = {
        "schema_version": 1, "source": source_commit(), "definition_sha256": digest(CONFIG), "origins": config["origins"],
        "upstream": pins, "source_citation": config["source_citation"], "source_rights": config["source_rights"],
        "cohorts": cohorts, "scales": scales, "trained_coefficients": trained, "validation": choice,
        "calibrations": radii, "predictions": predictions, "scores": score(predictions, cohorts, config),
    }
    write_json(RESULT, data)
    return data
