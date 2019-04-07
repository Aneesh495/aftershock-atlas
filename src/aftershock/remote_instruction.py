"""Aggregate Household Pulse education responses with adult replicate weights."""

from __future__ import annotations

import math
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from .privacy import Disclosure
from .survey_design import MEMBERS, archive_rows


def measures(config: dict) -> list[tuple[str, str, float, bool]]:
    result = [(key, label, 1.0, True) for key, label in config["items"].items()]
    for key, item in config["time_items"].items():
        result.append((key, item["label"] + " (mean hours)", float(item["maximum"]), False))
        result.append((key + "_ZERO", item["label"] + " (zero hours)", 1.0, True))
        result.append((key + "_TOP", item["label"] + " (at top code)", 1.0, True))
    return result


def respondent_values(row: dict, config: dict) -> list[float]:
    missing = config["missing_code"]
    not_selected = config["not_selected_code"]
    selected = config["selected_code"]
    result = []
    for key in config["items"]:
        code = int(row[key])
        if code not in {missing, not_selected, selected}:
            raise ValueError("Unknown remote instruction choice code")
        result.append(math.nan if code == missing else float(code == selected))
    for key, item in config["time_items"].items():
        hours = float(row[key])
        maximum = item["maximum"]
        if hours in {missing, not_selected}:
            result.extend((math.nan, math.nan, math.nan))
        elif 0 <= hours <= maximum:
            result.extend((float(hours), float(hours == 0), float(hours == maximum)))
        else:
            raise ValueError("Remote instruction hours outside source bounds")
    return result


def group_names(config: dict) -> list[str]:
    return ["All eligible adults", *config["gender_labels"].values(),
            *(f"Age {a} to {b}" if b < 120 else f"Age {a}+" for a, b in config["age_bands"])]


def respondent_groups(row: dict, config: dict) -> list[int]:
    gender = config["gender_labels"].get(row["EGENDER"])
    age = 2020 - int(row["TBIRTH_YEAR"])
    if gender is None or not 18 <= age <= 88:
        raise ValueError("Unknown Household Pulse demographic code")
    labels = group_names(config)
    for a, b in config["age_bands"]:
        if a <= age <= b:
            return [0, labels.index(gender), labels.index(f"Age {a} to {b}" if b < 120 else f"Age {a}+")]
    raise ValueError("Household Pulse age outside registered groups")


def instruction_estimates(path: Path, config: dict, source_hash: str) -> dict:
    groups = group_names(config)
    definitions = measures(config)
    shape = (len(groups), len(definitions))
    sums = np.zeros((*shape, 81))
    denominators = np.zeros_like(sums)
    squares = np.zeros(shape)
    n = np.zeros(shape, dtype=int)
    positives = np.zeros_like(n)
    eligible_n = np.zeros(len(groups), dtype=int)
    eligible_weight = np.zeros(len(groups))
    roster = {}
    enrolled_missing = 0
    with ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != len(MEMBERS) or set(archive.namelist()) != MEMBERS:
            raise ValueError("Unexpected Household Pulse ZIP members")
        if sum(m.file_size for m in members) > 120_000_000:
            raise ValueError("Expanded Household Pulse ZIP exceeds study maximum")
        for row in archive_rows(archive, "pulse2020_puf_01.csv"):
            key = row["SCRAM"], row["WEEK"]
            if key in roster or key[1] != str(config["week"]) or not key[0]:
                raise ValueError("Duplicate or wrong-week remote instruction record")
            weight = float(row["PWEIGHT"])
            if not math.isfinite(weight) or weight <= 0:
                raise ValueError("Invalid remote instruction person weight")
            roster[key] = None
            code = int(row[config["eligibility"]])
            if code == config["missing_code"]:
                enrolled_missing += 1
            elif code == config["eligible_code"]:
                membership = respondent_groups(row, config)
                values = np.asarray(respondent_values(row, config))
                roster[key] = membership, values, weight
                valid = np.isfinite(values)
                for g in membership:
                    eligible_n[g] += 1
                    eligible_weight[g] += weight
                    n[g, valid] += 1
                    positives[g, valid] += values[valid] > 0
                    squares[g, valid] += weight * weight
            elif code != config["not_selected_code"]:
                raise ValueError("Unknown Household Pulse enrollment status")
        sample_rows = len(roster)
        for row in archive_rows(archive, "pulse2020_repwgt_puf_01.csv"):
            key = row["SCRAM"], row["WEEK"]
            if key not in roster:
                raise ValueError("Missing or duplicated instruction replicate partner")
            data = roster.pop(key)
            if data is None:
                continue
            membership, values, full_weight = data
            weights = np.array([full_weight, *(float(row[f"PWEIGHT{i}"]) for i in range(1, 81))])
            if not np.isfinite(weights).all() or (weights < 0).any():
                raise ValueError("Invalid remote instruction replicate weights")
            valid = np.isfinite(values)
            for g in membership:
                denominators[g, valid] += weights
                sums[g, valid] += values[valid, None] * weights
        if roster or sample_rows != 74_413:
            raise ValueError("Incomplete frozen Household Pulse roster")

    rows = []
    disclosure = Disclosure(minimum_cell=config["minimum_complete"])
    for g, group in enumerate(groups):
        for j, (key, label, maximum, binary) in enumerate(definitions):
            sample = int(n[g, j])
            output = {
                "metric": key, "label": label, "group": group, "source_hash": source_hash,
                "kind": "survey_estimate", "unit": "percent of eligible adults" if binary else "reported hours",
                "population": config["universe"], "event_start": "2020-04-23", "event_end": "2020-05-05",
                "value": None, "se": None, "lower": None, "upper": None, "denominator": None,
                "complete_respondents": None, "eligible_respondents": None, "kish_effective_n": None,
                "weighted_item_missing_fraction": None, "item_missing_lower": None, "item_missing_upper": None,
            }
            reasons = []
            if sample < config["minimum_complete"] or (denominators[g, j] <= 0).any():
                reasons.append("insufficient complete response")
            elif binary and min(positives[g, j], sample - positives[g, j]) < config["minimum_outcome_count"]:
                reasons.append("small response category")
            if not reasons:
                ratios = sums[g, j] / denominators[g, j]
                estimate = float(ratios[0])
                se = float(np.sqrt(config["design_factor"] * np.sum((ratios[1:] - estimate) ** 2)))
                if estimate and se / estimate > disclosure.maximum_relative_se:
                    reasons.append("unstable estimate")
                else:
                    radius = config["interval_critical_value"] * se
                    scale = 100.0 if binary else 1.0
                    complete_weight = float(denominators[g, j, 0])
                    eligible = float(eligible_weight[g])
                    missing = max(0.0, eligible - complete_weight)
                    output.update(
                        value=scale * estimate, se=scale * se, lower=scale * max(0.0, estimate - radius),
                        upper=scale * min(maximum, estimate + radius), denominator=complete_weight,
                        complete_respondents=sample, eligible_respondents=int(eligible_n[g]),
                        kish_effective_n=complete_weight ** 2 / float(squares[g, j]),
                        weighted_item_missing_fraction=missing / eligible,
                        item_missing_lower=scale * float(sums[g, j, 0]) / eligible,
                        item_missing_upper=scale * (float(sums[g, j, 0]) + missing * maximum) / eligible,
                    )
            output["suppressed"] = bool(reasons)
            output["suppression_reason"] = reasons[0] if reasons else None
            rows.append(output)

    return {
        "rows": rows, "respondent_rows": sample_rows, "unknown_eligibility_rows": enrolled_missing,
        "replicates": 80, "variance_factor": config["design_factor"],
        "provider_weighted_unit_response_percent": 3.8,
        "source_sha256": source_hash, "population": config["universe"],
        "limitation": "Week 1 adult proxy reports. Teaching choices can overlap. Hours are top-coded. Intervals omit unit nonresponse bias.",
    }
