"""Compare design-based results around the Household Pulse recall-period change."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from .acquire import Source, acquire_one
from .io import ROOT, digest, read_json, source_commit, write_json
from .resources import usage
from .survey_design import INDICATORS, archive_rows, replicate_estimate

CONFIG = ROOT / "configs/survey-bridge-v5.json"
PINS = ROOT / "configs/survey-bridge-inputs.json"
RAW = ROOT / "data/private-survey"
RESULT = ROOT / "data/results/survey-bridge.json"


def acquire_bridge() -> dict:
    pins = read_json(PINS)
    for key, pin in pins.items():
        received = acquire_one(Source(**{k: pin[k] for k in Source.__dataclass_fields__}), RAW)
        if received["bytes"] != pin["bytes"] or received["sha256"] != pin["sha256"]:
            raise ValueError(f"Survey bridge source bytes changed: {key}")
    return {"sources": len(pins)}


def checked_path(raw: Path, pin: dict) -> Path:
    path = raw / pin["path"]
    if path.stat().st_size != pin["bytes"] or digest(path) != pin["sha256"]:
        raise ValueError(f"Survey bridge source identity mismatch: {pin['id']}")
    return path


def source_groups(config: dict) -> list[tuple[str, str]]:
    return [("national", "United States"), *(
        (group, label) for group, values in config["subgroups"].items() for label in values
    )]


def codes(row: dict) -> tuple[int, int, int]:
    origin, race, income = (int(row[key]) for key in ("RHISPANIC", "RRACE", "INCOME"))
    if origin not in {1, 2} or race not in {1, 2, 3, 4} or income not in {-99, -88, *range(1, 9)}:
        raise ValueError("Unexpected survey bridge group code")
    return origin, race, income


def group_indices(row: dict, config: dict, groups: list[tuple[str, str]]) -> list[int]:
    origin, race, income = codes(row)
    selection = {"race_origin": [origin, None if origin == 2 else race], "income": income}
    matches = [0]
    for i, (kind, label) in enumerate(groups[1:], 1):
        rule = config["subgroups"][kind][label]
        if (selection[kind] == rule if kind == "race_origin" else income in rule):
            matches.append(i)
    if len(matches) != 3:
        raise ValueError("Survey bridge subgroup partition is inconsistent")
    return matches


def bridge_scores(row: dict, config: dict) -> tuple[float, float, float]:
    results = []
    for series in ("anxiety", "depression"):
        values = [int(row[item]) for item in config["items"][series]]
        if any(value not in {-99, -88, 1, 2, 3, 4} for value in values):
            raise ValueError("Unexpected Pulse symptom item code")
        results.append(float(sum(values) >= 5) if min(values) > 0 else math.nan)
    anxiety, depression = results
    any_symptoms = max(results) if all(math.isfinite(score) for score in results) else math.nan
    return anxiety, depression, any_symptoms


def published_points(path: Path, definitions: dict) -> dict:
    source_groups = {"National Estimate", "By Race/Hispanic ethnicity"}
    lookup = {(scope["start"], scope["end"], scope["phase"]): week for week, scope in definitions.items()}
    values = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["time_period_start_date"][:10], row["time_period_end_date"][:10], row["phase"])
            week = lookup.get(key)
            if week is None or row["state"] != "United States" or row["group"] not in source_groups:
                continue
            identity = (week, row["subgroup"], row["indicator"])
            if identity in values:
                raise ValueError("Duplicate released Pulse estimate")
            values[identity] = float(row["value"]) if row["value"] else None
    return values


def totals(path: Path, week: str, config: dict, groups: list[tuple[str, str]]) -> dict:
    stem = "pulse2021"
    participants = f"{stem}_puf_{week}.csv"
    replication = f"{stem}_repwgt_puf_{week}.csv"
    dictionary = f"{stem}_data.dictionary_CSV_{week}.xlsx"
    members = {participants, replication, dictionary}
    replicates = config["person_replicates"]
    dimensions = (len(groups), len(INDICATORS))
    denominators = np.zeros((*dimensions, replicates + 1))
    numerators = np.zeros_like(denominators)
    eligible = np.zeros(len(groups))
    complete = np.zeros(dimensions, dtype=int)
    positive = np.zeros_like(complete)
    squares = np.zeros(dimensions)
    records = {}
    with ZipFile(path) as zip_file:
        inventory = zip_file.infolist()
        if len(inventory) != 3 or set(zip_file.namelist()) != members or sum(x.file_size for x in inventory) > 250_000_000:
            raise ValueError("Survey bridge ZIP inventory or expansion mismatch")
        for row in archive_rows(zip_file, participants):
            key = row["SCRAM"]
            if not key or key in records or row["WEEK"] != week:
                raise ValueError("Duplicate respondent or incorrect survey week")
            full = float(row["PWEIGHT"])
            if not math.isfinite(full) or full <= 0:
                raise ValueError("Invalid adult person weight")
            indices = group_indices(row, config, groups)
            scores = np.array(bridge_scores(row, config))
            valid = np.isfinite(scores)
            for i in indices:
                eligible[i] += full
                complete[i, valid] += 1
                positive[i, valid] += scores[valid].astype(int)
                squares[i, valid] += full * full
            records[key] = full, indices, scores
        if len(records) != config["waves"][week]["responses"]:
            raise ValueError("Wave response count differs from official Census release")
        for row in archive_rows(zip_file, replication):
            key = row["SCRAM"]
            if key not in records or row["WEEK"] != week:
                raise ValueError("Missing, duplicate or incorrect-wave replicate partner")
            full, indices, scores = records.pop(key)
            weights = np.array([full, *(float(row[f"PWEIGHT{i}"]) for i in range(1, replicates + 1))])
            if not np.isfinite(weights).all() or (weights < 0).any():
                raise ValueError("Invalid Census person replicate weight")
            valid = np.isfinite(scores)
            pos = scores == 1
            for i in indices:
                denominators[i, valid] += weights
                numerators[i, pos] += weights
        if records:
            raise ValueError("Unmatched adult responses")
    return {"denominators": denominators, "numerators": numerators, "complete": complete,
            "positive": positive, "eligible": eligible, "squares": squares}


def cells(
    summary: dict, config: dict, week: str, groups: list[tuple[str, str]], points: dict,
) -> list[dict]:
    rows = []
    for i, (kind, label) in enumerate(groups):
        eligible = float(summary["eligible"][i])
        for j, metric in enumerate(INDICATORS):
            n = int(summary["complete"][i, j])
            successes = int(summary["positive"][i, j])
            numerator = summary["numerators"][i, j]
            denominator = summary["denominators"][i, j]
            population = {"group": label, "group_kind": kind, "metric": metric, "week": int(week)}
            reason = None
            minimum = config["minimum_in_each_outcome"]
            if n < config["minimum_complete"] or min(successes, n - successes) < minimum:
                reason = "insufficient complete response"
            else:
                estimate, se = replicate_estimate(numerator, denominator)
                if se / estimate > config["maximum_relative_standard_error"]:
                    reason = "unstable sampling estimate"
            if reason is not None:
                rows.append({**population, "suppressed": True, "suppression_reason": reason,
                             "value": None, "lower": None, "upper": None, "denominator": None})
                continue
            released = points.get((week, label, metric))
            gap = estimate * 100 - released if released is not None else None
            radius = se * 1.959963984540054
            rows.append({**population, "suppressed": False, "suppression_reason": None,
                         "complete_respondents": n, "value": estimate * 100, "se": se * 100,
                         "lower": max(0, estimate - radius) * 100, "upper": min(1, estimate + radius) * 100,
                         "weighted_eligible_adults": eligible, "denominator": float(denominator[0]),
                         "weighted_item_missing_fraction": float(1 - denominator[0] / eligible),
                         "item_missing_lower": float(100 * numerator[0] / eligible),
                         "item_missing_upper": float(100 * (numerator[0] + eligible - denominator[0]) / eligible),
                         "kish_effective_n": float(denominator[0] ** 2 / summary["squares"][i, j]),
                         "provider_value": released, "provider_difference_pp": gap,
                         "provider_agreement": abs(gap) <= config["provider_agreement_pp"] if gap is not None else None})
    return rows


def run_bridge() -> dict:
    usage(25_000_000)
    config, pins = read_json(CONFIG), read_json(PINS)
    national = read_json(ROOT / "configs/data-inputs.json")["survey"]
    points = published_points(checked_path(ROOT / "data/raw", national), config["waves"])
    groups = source_groups(config)
    surveys = {}
    for week, scope in config["waves"].items():
        archive = checked_path(RAW, pins[f"hps_week{week}"])
        for name in ("design", "questions"):
            checked_path(RAW, pins[f"hps_week{week}_{name}"])
        aggregates = totals(archive, week, config, groups)
        rows = cells(aggregates, config, week, groups, points)
        sensitivity = []
        response = scope["weighted_unit_response_percent"] / 100
        for row in rows:
            if row["group_kind"] == "national" and not row["suppressed"]:
                for shift in (-10, -5, 5, 10):
                    assumed = min(100, max(0, row["value"] + shift))
                    sensitivity.append({"metric": row["metric"], "assumed_nonrespondent_shift_pp": shift,
                                        "scenario_percent": response * row["value"] + (1 - response) * assumed})
        surveys[week] = {"wave": scope, "source_sha256": pins[f"hps_week{week}"]["sha256"],
                         "rows": rows, "selection_sensitivity": sensitivity}
    result = {"schema_version": 1, "source": source_commit(), "definition_sha256": digest(CONFIG),
              "private_input_manifest_sha256": digest(PINS), "aggregate_comparator_sha256": national["sha256"],
              "variance_factor": config["variance_factor"], "person_replicates": config["person_replicates"],
              "population": config["population"], "context": config["context"], "comparability": config["wave_comparability"],
              "sensitivity_basis": "Hypothetical unit nonresponse mixture uses provider household response rates as scenario inputs.",
              "waves": surveys}
    write_json(RESULT, result)
    return result
