"""Stream a lawful public-use survey into disclosure-checked design estimates."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from .acquire import Source, acquire_one
from .io import ROOT, digest, read_json, write_json
from .privacy import Disclosure
from .resources import usage

INDICATORS = ("Symptoms of Anxiety Disorder", "Symptoms of Depressive Disorder",
              "Symptoms of Anxiety Disorder or Depressive Disorder")
GROUPS = ("United States", "Male", "Female", "Hispanic or Latino",
          "Non-Hispanic White, single race", "Non-Hispanic Black, single race",
          "Non-Hispanic Asian, single race", "Non-Hispanic, other races and multiple races")
MEMBERS = {"pulse2020_puf_01.csv", "pulse2020_repwgt_puf_01.csv", "pulse2020_data.dictionary_CSV_01.xlsx"}


def acquire_design(refresh: bool = False) -> dict:
    pinned = read_json(ROOT / "configs/survey-inputs.json")
    raw = ROOT / "data/private-survey"
    result = {}
    for key, record in pinned.items():
        source = Source(**{k: record[k] for k in Source.__dataclass_fields__})
        received = acquire_one(source, raw, refresh)
        if received["sha256"] != record["sha256"]:
            raise ValueError("Survey extension source drift: " + key)
        # Frozen timing is preserved on restoration; present acquisition remains in its receipt.
        result[key] = record
    write_json(raw / "index.json", result)
    return {key: "acquired" for key in result}


def archive_rows(archive: ZipFile, name: str):
    with archive.open(name) as binary:
        reader = csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8-sig", newline=""))
        for i, row in enumerate(reader):
            if i >= 100_000 or None in row:
                raise ValueError("Survey row bound or malformed CSV")
            yield row


def memberships(row: dict) -> list[int]:
    gender, hispanic, race = int(row["EGENDER"]), int(row["RHISPANIC"]), int(row["RRACE"])
    result = [0]
    if gender in {1, 2}:
        result.append(gender)
    if hispanic == 2:
        result.append(3)
    elif hispanic == 1 and race in {1, 2, 3, 4}:
        result.append(3 + race)
    return result


def symptom_scores(row: dict) -> np.ndarray:
    items = np.array([int(row[k]) for k in ("ANXIOUS", "WORRY", "INTEREST", "DOWN")])
    valid = (items >= 1) & (items <= 4)
    anxiety = float(items[:2].sum() - 2 >= 3) if valid[:2].all() else np.nan
    depression = float(items[2:].sum() - 2 >= 3) if valid[2:].all() else np.nan
    combined = float(anxiety == 1 or depression == 1) if valid.all() else np.nan
    return np.array([anxiety, depression, combined])


def replicate_estimate(numerator: np.ndarray, denominator: np.ndarray) -> tuple[float, float]:
    if numerator.shape != (81,) or denominator.shape != (81,) or (denominator <= 0).any():
        raise ValueError("Full weight plus 80 positive replicate denominators required")
    estimates = numerator / denominator
    if not np.isfinite(estimates).all() or ((estimates < 0) | (estimates > 1)).any():
        raise ValueError("Invalid survey replicate estimate")
    return float(estimates[0]), float(np.sqrt(4 / 80 * np.sum((estimates[1:] - estimates[0]) ** 2)))


def released_cell(group: str, metric: str, n: int, payload: dict) -> dict:
    unstable = bool(payload.get("value") and payload.get("se", 0) / payload["value"] > .3)
    if n < 100 or unstable:
        return {"group": group, "metric": metric, "value": None, "lower": None, "upper": None,
                "denominator": None, "suppressed": True, "suppression_reason": "small or unstable complete-response cell"}
    return Disclosure(minimum_cell=100).apply({"group": group, "metric": metric, "sample_n": n, **payload})


def analyze_design(path: Path | None = None) -> dict:
    usage(300_000_000)
    sources = read_json(ROOT / "configs/survey-inputs.json")
    path = path or ROOT / "data/private-survey" / sources["hps_week1"]["path"]
    if digest(path) != sources["hps_week1"]["sha256"]:
        raise ValueError("Survey public-use archive identity mismatch")
    numerators = np.zeros((len(GROUPS), 3, 81))
    denominators = np.zeros_like(numerators)
    eligible_weight = np.zeros(len(GROUPS))
    count = np.zeros((len(GROUPS), 3), dtype=int)
    positive = np.zeros_like(count)
    eligible_count = np.zeros(len(GROUPS), dtype=int)
    weight_square = np.zeros((len(GROUPS), 3))
    records = {}
    with ZipFile(path) as archive:
        if set(archive.namelist()) != MEMBERS or sum(m.file_size for m in archive.infolist()) > 120_000_000:
            raise ValueError("Unexpected survey ZIP members or expansion")
        for row in archive_rows(archive, "pulse2020_puf_01.csv"):
            key = row["SCRAM"], row["WEEK"]
            if key in records or key[1] != "1":
                raise ValueError("Duplicate or wrong-week survey population")
            weight = float(row["PWEIGHT"])
            if not np.isfinite(weight) or weight <= 0:
                raise ValueError("Survey person weight must be positive")
            groups, scores = memberships(row), symptom_scores(row)
            records[key] = groups, scores, weight
            valid = np.isfinite(scores)
            for group in groups:
                eligible_count[group] += 1
                eligible_weight[group] += weight
                count[group, valid] += 1
                positive[group, valid] += scores[valid].astype(int)
                weight_square[group, valid] += weight ** 2
        sample_rows = len(records)
        for row in archive_rows(archive, "pulse2020_repwgt_puf_01.csv"):
            key = row["SCRAM"], row["WEEK"]
            if key not in records:
                raise ValueError("Missing or duplicate survey replicate partner")
            groups, scores, full = records.pop(key)
            weights = np.array([full] + [float(row[f"PWEIGHT{i}"]) for i in range(1, 81)])
            if not np.isfinite(weights).all() or (weights < 0).any():
                raise ValueError("Replicate weights must be finite and nonnegative")
            valid = np.isfinite(scores)
            for group in groups:
                denominators[group, valid] += weights
                numerators[group, valid] += scores[valid, None] * weights
        if records:
            raise ValueError("Unmatched survey public-use records")
    if sample_rows != 74_413:
        raise ValueError("Survey archive population differs from documented week 1")
    # Only aggregate accumulators survive the in-memory join.
    published = {}
    upstream = read_json(ROOT / "data/raw/index.json")["survey"]
    with (ROOT / "data/raw" / upstream["path"]).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["state"] == "United States" and row["time_period_start_date"][:10] == "2020-04-23":
                published[row["subgroup"], row["indicator"]] = float(row["value"]) if row["value"] else None
    rows = []
    for g, group in enumerate(GROUPS):
        for j, indicator in enumerate(INDICATORS):
            estimate, se = replicate_estimate(numerators[g, j], denominators[g, j])
            published_value = published.get((group, indicator))
            delta = 100 * estimate - published_value if published_value is not None else None
            radius = 1.959963984540054 * se
            rows.append(released_cell(group, indicator, int(count[g, j]), {
                "region": "USA", "event_start": "2020-04-23", "event_end": "2020-05-05", "phase": "1",
                "reference_days": 7, "value": estimate * 100, "se": se * 100,
                "lower": max(0, estimate - radius) * 100, "upper": min(1, estimate + radius) * 100,
                "denominator": float(denominators[g, j, 0]), "complete_respondents": int(count[g, j]),
                "eligible_respondents": int(eligible_count[g]),
                "weighted_item_missing_fraction": float(1 - denominators[g, j, 0] / eligible_weight[g]),
                "unweighted_percent": float(positive[g, j] / count[g, j] * 100),
                "kish_effective_n": float(denominators[g, j, 0] ** 2 / weight_square[g, j]),
                "published_value": published_value, "difference_pp": delta,
                "point_agreement": abs(delta) <= .15 if delta is not None else False,
                "item_missing_lower": float(numerators[g, j, 0] / eligible_weight[g] * 100),
                "item_missing_upper": float((numerators[g, j, 0] + eligible_weight[g] - denominators[g, j, 0]) / eligible_weight[g] * 100),
                "source_hash": sources["hps_week1"]["sha256"], "kind": "survey_estimate", "unit": "percent adults"}))
    sensitivity = []
    for row in rows:
        if row["group"] == "United States" and not row.get("suppressed"):
            p = row["value"] / 100
            for shift in (-.1, -.05, .05, .1):
                alternative = min(1, max(0, p + shift))
                sensitivity.append({"metric": row["metric"], "nonrespondent_shift_pp": shift * 100,
                    "scenario_percent": (.038 * p + .962 * alternative) * 100,
                    "interpretation": "selection sensitivity; weighted unit response is not a known adult response fraction"})
    result = {"protocol": "extension-v2-exploratory", "rows": rows, "respondent_rows": sample_rows,
              "replicates": 80, "variance_factor": .05, "interval_level": .95,
              "point_matches": sum(r.get("point_agreement", False) for r in rows),
              "point_comparisons": len(rows), "nonresponse_sensitivity": sensitivity,
              "contacted_sample_units": 1_867_126, "unweighted_response_fraction": 74_413 / 1_867_126,
              "provider_weighted_response_percent": 3.8, "independent_weight_recomputation": True,
              "raw_in_evidence": False, "sources": sources,
              "limitations": ["One week only; later wave weights are not replayed", "No restricted frame or raw nonrespondent outcomes",
                "Weighted person denominators differ across complete-item populations", "Sampling intervals omit nonresponse bias",
                "Normal sampling intervals differ from NCHS transformed presentation intervals", "Source-defined US categories have no universal biological meaning"]}
    write_json(ROOT / "data/results/survey-design.json", result)
    return result
