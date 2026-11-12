"""Independent source and scalar numerical replay for exploratory extensions."""
from __future__ import annotations

import csv
import io
import math
from collections import Counter
from zipfile import ZipFile

import numpy as np

from .io import ROOT, digest, read_json
from .verification import require


def verify_survey_design(bundle):
    pinned = read_json(ROOT / "configs/survey-inputs.json")
    require(read_json(bundle / "SURVEY_INPUTS.json") == pinned, "Survey input metadata differs from trusted acquisition")
    result = read_json(bundle / "survey-design.json")
    require(result["variance_factor"] == 4 / 80 and result["replicates"] == 80, "Invalid survey variance factor")
    require(result["raw_in_evidence"] is False, "Raw survey evidence must be excluded")
    for path in bundle.rglob("*.zip"):
        with ZipFile(path) as zipped:
            require(not any("pulse2020" in n for n in zipped.namelist()), "Respondent archive leaked into evidence")
    for source in pinned.values():
        path = ROOT / "data/private-survey" / source["path"]
        require(path.is_file() and digest(path) == source["sha256"], "Private survey source identity mismatch; run make survey-data")
    estimates = {(row["group"], row["metric"]): row for row in result["rows"]}
    labels = ["United States", "Male", "Female", "Hispanic or Latino", "Non-Hispanic White, single race",
              "Non-Hispanic Black, single race", "Non-Hispanic Asian, single race", "Non-Hispanic, other races and multiple races"]
    indicators = ["Symptoms of Anxiety Disorder", "Symptoms of Depressive Disorder",
                  "Symptoms of Anxiety Disorder or Depressive Disorder"]
    require(set(estimates) == {(g, m) for g in labels for m in indicators}, "Survey population reclassified")
    numerator = np.zeros((24, 81))
    denominator = np.zeros_like(numerator)
    counts = np.zeros(24, dtype=int)
    all_weights = np.zeros(8)
    participants = {}
    def rows(zipped, name):
        with zipped.open(name) as raw:
            yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))
    with ZipFile(ROOT / "data/private-survey" / pinned["hps_week1"]["path"]) as archive:
        for row in rows(archive, "pulse2020_puf_01.csv"):
            key = row["SCRAM"], row["WEEK"]
            require(key not in participants and key[1] == "1", "Duplicate survey population")
            groups = [0]
            if row["EGENDER"] in {"1", "2"}:
                groups.append(int(row["EGENDER"]))
            if row["RHISPANIC"] == "2":
                groups.append(3)
            elif row["RHISPANIC"] == "1" and row["RRACE"] in {"1", "2", "3", "4"}:
                groups.append(3 + int(row["RRACE"]))
            a, b, c, d = [int(row[name]) for name in ("ANXIOUS", "WORRY", "INTEREST", "DOWN")]
            anxiety = int(a + b >= 5) if 1 <= a <= 4 and 1 <= b <= 4 else None
            depressive = int(c + d >= 5) if 1 <= c <= 4 and 1 <= d <= 4 else None
            combined = int(bool(anxiety or depressive)) if anxiety is not None and depressive is not None else None
            cells = [(g * 3 + j, y) for g in groups for j, y in enumerate((anxiety, depressive, combined)) if y is not None]
            weight = float(row["PWEIGHT"])
            for g in groups:
                all_weights[g] += weight
            for cell, y in cells:
                numerator[cell, 0] += weight * y
                denominator[cell, 0] += weight
                counts[cell] += 1
            participants[key] = cells
        sample_n = len(participants)
        for row in rows(archive, "pulse2020_repwgt_puf_01.csv"):
            key = row["SCRAM"], row["WEEK"]
            require(key in participants, "Replicate join mismatch")
            cells = participants.pop(key)
            weights = np.array([float(row[f"PWEIGHT{i}"]) for i in range(1, 81)])
            for cell, y in cells:
                numerator[cell, 1:] += weights * y
                denominator[cell, 1:] += weights
        require(not participants and sample_n == result["respondent_rows"] == 74_413, "Survey join population mismatch")
    published = {}
    published_source = read_json(bundle / "DATASETS.json")["sources"]["survey"]
    with (ROOT / "data/raw" / published_source["path"]).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["state"] == "United States" and row["time_period_start_date"][:10] == "2020-04-23" and row["value"]:
                published[row["subgroup"], row["indicator"]] = float(row["value"])
    matched = 0
    for g, group in enumerate(labels):
        for j, indicator in enumerate(indicators):
            cell = g * 3 + j
            row = estimates[group, indicator]
            require(counts[cell] >= 100 and not row.get("suppressed"), "Invalid released survey support")
            require(row["complete_respondents"] == counts[cell], "Survey respondent denominator mismatch")
            require(math.isclose(row["denominator"], denominator[cell, 0], rel_tol=1e-10), "Survey weighted denominator mismatch")
            p = numerator[cell] / denominator[cell]
            se = math.sqrt(sum((x - p[0]) ** 2 for x in p[1:]) / 20)
            require(math.isclose(row["value"], p[0] * 100, rel_tol=1e-10), "Survey numerator replay mismatch")
            require(math.isclose(row["se"], se * 100, rel_tol=1e-10), "Survey replicate variance mismatch")
            require(math.isclose(row["weighted_item_missing_fraction"], 1 - denominator[cell, 0] / all_weights[g], abs_tol=1e-10), "Survey missingness denominator mismatch")
            require(math.isclose(row["lower"], max(0, p[0] - 1.959963984540054 * se) * 100, abs_tol=1e-9), "Survey sampling interval mismatch")
            require(math.isclose(row["upper"], min(1, p[0] + 1.959963984540054 * se) * 100, abs_tol=1e-9), "Survey sampling interval mismatch")
            reference = published[group, indicator]
            require(row["published_value"] == reference, "Survey comparison detached from published source")
            difference = p[0] * 100 - reference
            require(math.isclose(row["difference_pp"], difference, abs_tol=1e-9), "Survey published difference mismatch")
            require(row["point_agreement"] == (abs(difference) <= .15), "Survey missed tolerance reclassified")
            matched += abs(difference) <= .15
    require(matched == result["point_matches"], "Survey agreement summary mismatch")
    require(result["provider_weighted_response_percent"] == 3.8 and result["contacted_sample_units"] == 1_867_126, "Survey nonresponse definition mismatch")
    for row in read_json(bundle / "surveys.json")["rows"]:
        require(row["reference_days"] == (7 if row["event_start"] < "2021-07-21" else 14), "Survey reference-period reclassified")
    return {"public_use_records": sample_n, "aggregate_design_cells": 24, "replicates": 80, "raw_in_bundle": False}


def scalar_dynamic(values, parameters):
    prior, log_tau, log_ql, log_qs, log_r, phi = parameters
    tau, ql, qs, r = [math.exp(x) for x in (log_tau, log_ql, log_qs, log_r)]
    first = next(i for i, y in enumerate(values) if math.isfinite(y))
    origin = values[first]
    a, b, p00, p01, p11 = 0., prior, r, 0., tau
    for t in range(first + 1, 5):
        a, b = a + phi * b, phi * b
        p00, p01, p11 = p00 + 2 * phi * p01 + phi ** 2 * p11 + ql, phi * p01 + phi ** 2 * p11, phi ** 2 * p11 + qs
        if t < 4 and math.isfinite(values[t]):
            residual = values[t] - origin - a
            k0, k1 = p00 / (p00 + r), p01 / (p00 + r)
            a, b = a + k0 * residual, b + k1 * residual
            p00, p01, p11 = p00 * (1 - k0), p01 * (1 - k0), p11 - k1 * p01
    return origin + a, p00 + r


def verify_dynamic(bundle, annual):
    result = read_json(bundle / "dynamic.json")
    rows = read_json(bundle / "dynamic-predictions.json")
    require(result["protocol"] == "extension-v2-exploratory", "Dynamic evidence relabeled as confirmatory")
    require(result["protocol_sha256"] == digest(ROOT / "docs/EXTENSION_PLAN_V2.md"), "Dynamic extension protocol mismatch")
    keys = read_json(bundle / "models/replay-keys.json")
    country_counts = Counter(k["region"] for k in keys if k["target_year"] <= 2015 and not k["held_out_region"])
    fits = {fit["metric"]: fit for fit in result["fits"]}
    require(set(fits) == {"employment", "gdp", "school", "immunization", "mortality", "life_expectancy"}, "Dynamic outcome family mismatch")
    expected = set()
    def level(region, metric, year):
        y = annual.get((region, metric, year), math.nan)
        return math.log1p(y) if metric == "gdp" and math.isfinite(y) else y
    for metric, fit in fits.items():
        train, validation = [], []
        for key in keys:
            region, year = key["region"], key["target_year"]
            current, previous = level(region, metric, year), level(region, metric, year - 1)
            if not math.isfinite(current) or not math.isfinite(previous):
                continue
            if year <= 2015 and not key["held_out_region"]:
                train.append((region, year, current - previous))
            elif 2016 <= year <= 2018 and not key["held_out_region"]:
                validation.append((region, year, current))
            if 2019 <= year <= 2024:
                expected.add((region, year, metric))
        scale = max(float(np.std([r[2] for r in train])), 1e-4)
        require(math.isclose(scale, fit["scale"], rel_tol=1e-10), "Dynamic scale fitted on wrong population")
        require(len(train) == fit["training_rows"], "Dynamic training population mismatch")
        params = fit["chosen"]["parameters"]
        weights, likelihood = [], []
        for region, year, _ in train:
            values = [level(region, metric, y) / scale for y in range(year - 4, year)]
            mu, variance = scalar_dynamic(values, params)
            truth = level(region, metric, year) / scale
            likelihood.append(.5 * (math.log(2 * math.pi * variance) + (truth - mu) ** 2 / variance))
            weights.append(1 / country_counts[region])
        require(math.isclose(float(np.average(likelihood, weights=weights)), fit["chosen"]["training_nll"], abs_tol=1e-8), "Dynamic training likelihood replay mismatch")
        residuals = []
        for region, year, truth in validation:
            mu, variance = scalar_dynamic([level(region, metric, y) / scale for y in range(year - 4, year)], params)
            residuals.append(abs(truth / scale - mu) / math.sqrt(variance))
        residuals.sort()
        calibration = max(.01, residuals[min(len(residuals) - 1, math.ceil((len(residuals) + 1) * .9) - 1)])
        for row in (r for r in rows if r["metric"] == metric):
            region, year = row["region"], row["target_year"]
            mu, variance = scalar_dynamic([level(region, metric, y) / scale for y in range(year - 4, year)], params)
            require(math.isclose(mu * scale, row["mean_t"], abs_tol=1e-8), "Dynamic saved-parameter mean replay failed")
            require(math.isclose(math.sqrt(variance) * scale, row["sd_t"], abs_tol=1e-8), "Dynamic predictive variance replay failed")
            require(math.isclose(calibration, row["calibration_multiplier"], abs_tol=1e-8), "Dynamic validation calibration population mismatch")
    require({(r["region"], r["target_year"], r["metric"]) for r in rows} == expected, "Dynamic prediction population mismatch")
    return {"replayed_predictions": len(rows), "outcome_families": len(fits), "exploratory": True}
