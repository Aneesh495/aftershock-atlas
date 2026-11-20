"""Check standardization, suppression and within-wave uncertainty from raw matrices."""
from __future__ import annotations

import math
import re
from html import unescape
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from scipy.special import ndtr

from .io import ROOT, contained, digest, read_json
from .verification import require
from .verify_measurement import same, spreadsheet_cells
from .verify_survey_bridge import compare, estimands, read_matrix


def pinned(root: Path, pin: dict) -> Path:
    file = contained(root, pin["path"])
    require(file.stat().st_size == pin["bytes"] and digest(file) == pin["sha256"], "Social context raw input differs")
    return file


def source_standard(file: Path, config: dict) -> np.ndarray:
    text = file.read_text(encoding="utf-8")
    table = unescape(text[text.index("AgeAdj-Table II. Projected year 2000 U.S. standard population and age groups"):])
    records = {}
    for content in re.findall(r"<tr>(.*?)</tr>", table, flags=re.S):
        label = re.search(r"<th[^>]*>([^<]+)</th>", content)
        data = re.findall(r"<td[^>]*>([^<]+)</td>", content)
        if label and len(data) == 3 and re.fullmatch(r"[0-9,]+", data[-1]):
            records.setdefault(label[1].strip(), int(data[-1].replace(",", "")))
    masses = []
    for band in config["age_bands"]:
        observed = {name: records[name] for name in band["standard_components"]}
        require(observed == band["standard_components"], "NCHS age-specific standard-million weight substituted")
        masses.append(sum(observed.values()))
    return np.array(masses) / sum(masses)


def cell(group: np.ndarray, band: np.ndarray, active: np.ndarray, responded: np.ndarray,
         positive: np.ndarray, weights: np.ndarray, standard: np.ndarray, bridge: dict) -> tuple:
    empty = dict.fromkeys(("adjusted_pct", "crude_pct", "se_pp", "lower", "upper", "complete_adults",
                          "weighted_complete", "item_missing_pct", "item_missing_lower", "item_missing_upper"))
    empty["suppressed"] = True
    selected = group & active & (band >= 0)
    n = 0
    totals, successes, eligible = [], [], []
    for ordinal in range(len(standard)):
        qualified = selected & (band == ordinal)
        complete = qualified & responded
        cases = complete & positive
        total, yes = int(complete.sum()), int(cases.sum())
        if total < bridge["minimum_complete"] or min(yes, total - yes) < bridge["minimum_in_each_outcome"]:
            return empty, None
        n += total
        totals.append(np.add.reduce(weights[complete], axis=0))
        successes.append(np.add.reduce(weights[cases], axis=0))
        eligible.append(float(weights[qualified, 0].sum()))
    full = np.vstack(totals)
    case = np.vstack(successes)
    if not (full > 0).all():
        return empty, None
    scores = np.sum((case / full) * standard[:, None], axis=0)
    point = scores[0]
    spread = np.linalg.norm(scores[1:] - point) / math.sqrt(20)
    if point <= 0 or spread / point > bridge["maximum_relative_standard_error"]:
        return empty, None
    weighted = full[:, 0].sum()
    eligible = np.asarray(eligible)
    missing = np.maximum(0, eligible - full[:, 0])
    lowest = (case[:, 0] / eligible * standard).sum()
    highest = ((case[:, 0] + missing) / eligible * standard).sum()
    return {
        "suppressed": False, "adjusted_pct": float(point * 100), "crude_pct": float(case[:, 0].sum() / weighted * 100),
        "se_pp": float(spread * 100), "lower": float(max(0, point - 1.959963984540054 * spread) * 100),
        "upper": float(min(1, point + 1.959963984540054 * spread) * 100), "complete_adults": n,
        "weighted_complete": float(weighted), "item_missing_pct": float(100 * missing.sum() / eligible.sum()),
        "item_missing_lower": float(100 * lowest), "item_missing_upper": float(100 * highest),
    }, scores


def verify_comparisons(published: list, tested: dict, references: dict, practical: float) -> int:
    lookup = {(r["group_kind"], r["group"], r["metric"]): r for r in published}
    expected = {key for key in tested if key[0] in references and key[1] != references[key[0]]}
    require(set(lookup) == expected and len(lookup) == len(published), "Social context comparator population changed")
    probabilities: dict = {}
    verified = 0
    for family, group, metric in expected:
        key = (family, group, metric)
        actual = lookup[key]
        baseline = references[family]
        require(actual["reference"] == baseline and len(actual["estimates"]) == 2, "Social context baseline or sensitivity changed")
        for mode, given in zip(("primary", "birthday_sensitivity"), actual["estimates"], strict=True):
            wanted = dict.fromkeys(("difference_pp", "se_pp", "lower", "upper", "crude_difference_pp",
                                    "large_difference", "p", "q"))
            wanted["mode"] = mode
            case, a = tested[key][mode]
            ref, b = tested[family, baseline, metric][mode]
            if a is not None and b is not None:
                difference = a[0] * 100 - b[0] * 100
                error = np.linalg.norm((a[1:] - a[0]) - (b[1:] - b[0])) * 100 / math.sqrt(20)
                critical = 1.959963984540054 * error
                wanted.update(difference_pp=float(difference), se_pp=float(error), lower=float(difference - critical),
                              upper=float(difference + critical), large_difference=bool(abs(difference) >= practical),
                              crude_difference_pp=case["crude_pct"] - ref["crude_pct"],
                              p=float(2 * ndtr(-abs(difference) / error)) if error > 0 else None)
                verified += 1
            q = given.get("q")
            compare({**given, "q": None}, wanted, "social subgroup contrast")
            if mode == "primary" and wanted["p"] is not None:
                probabilities.setdefault(metric, []).append((wanted["p"], q))
            else:
                require(q is None, "Social context multiplicity applied to an unavailable or sensitivity contrast")
    for trials in probabilities.values():
        tiesafe = sorted(trials, key=lambda p: p[0])
        total = len(trials)
        for i, (_, q) in enumerate(tiesafe):
            want = min(1.0, *(p * total / (j + 1) for j, (p, _) in enumerate(tiesafe) if j >= i))
            same(q, want, "Social context FDR adjustment changed")
    return verified


def verify_context(data: dict, source: str, public_raw: Path | None = None) -> dict:
    public_raw = public_raw or ROOT / "data/chronology/raw"
    private_raw = ROOT / "data/private-survey"
    cfg_path, manifest, bridge_path, protected = (
        ROOT / "configs" / name for name in ("social-context-v8.json", "social-context-inputs.json",
                                            "survey-bridge-v5.json", "survey-bridge-inputs.json")
    )
    config, public, bridge, private = map(read_json, (cfg_path, manifest, bridge_path, protected))
    require(data["source"] == source and data["schema_version"] == 1 and data["config_sha256"] == digest(cfg_path)
            and data["inputs_sha256"] == digest(manifest) and data["private_inputs_sha256"] == digest(protected),
            "Social context provenance differs")
    require(all(data[k] == config[k] for k in ("comparison_scope", "nonresponse_scope", "age_sensitivity", "standard_source"))
            and data["metric_labels"] == config["metrics"], "Social context interpretation or estimand changed")
    standard = source_standard(pinned(public_raw, public["nchs_2000_standard"]), config)
    require(set(data["age_standard"]) == {band["label"] for band in config["age_bands"]}, "Social context standard age bands changed")
    for band, weight in zip(config["age_bands"], standard, strict=True):
        same(data["age_standard"][band["label"]], float(weight), "Social context standard proportion changed")
    require(set(data["waves"]) == set(bridge["waves"]), "Social context survey waves changed")
    cells = withheld = comparisons = official_matches = 0
    for week, scope in bridge["waves"].items():
        release = data["waves"][week]
        pin = private[f"hps_week{week}"]
        require(release["wave"] == scope and release["source_sha256"] == pin["sha256"],
                "Social context wave or source changed")
        demographics, answers, weights = read_matrix(pinned(private_raw, pin), week, scope["responses"],
                                                      ("TBIRTH_YEAR", "TENURE", "CURFOODSUF"))
        origin, race, income, birth, tenure, food = demographics.T
        require(np.isin(origin, [1, 2]).all() and np.isin(race, [1, 2, 3, 4]).all()
                and np.isin(income, [-99, -88, *range(1, 9)]).all()
                and all(np.isin(v, [-99, -88, 1, 2, 3, 4]).all() for v in (tenure, food)),
                "Social context raw group or food-item domain differs")
        age = 2021 - birth
        require(((age >= 18) & (age <= 88)).all(), "Social context late-calendar-year age out of bounds")
        bands = np.select([(age >= b["lower"]) & (age <= b["upper"]) for b in config["age_bands"]],
                          list(range(len(config["age_bands"]))), default=-1)
        ok = ~np.isin(age, [b["lower"] for b in config["age_bands"]])
        masks = {("national", "United States"): age > 0}
        for label, (o, r) in bridge["subgroups"]["race_origin"].items():
            masks["race_origin", label] = (origin == o) if r is None else (origin == o) & (race == r)
        for group, answers_col in (("income", income), ("tenure", tenure)):
            for label, values in config[group].items():
                masks[group, label] = np.isin(answers_col, values)
        food_answered, food_insufficient = food > 0, food >= 3
        methods = {"food_insufficiency": (food_answered, food_insufficient), "mental_health_screen": estimands(answers)[-1]}
        observed = {(r["group_kind"], r["group"], r["metric"]): r for r in release["rows"]}
        require(set(observed) == {(*k, outcome) for k in masks for outcome in methods}
                and len(observed) == len(release["rows"]), "Social context estimate identity or disclosure scope changed")
        test = {}
        for (family, group), eligible in masks.items():
            for outcome, (answered, positive) in methods.items():
                identity = family, group, outcome
                recorded = observed[identity]
                require(set(recorded) == {"group_kind", "group", "metric", "primary", "birthday_sensitivity"},
                        "Social context output exposed unreleased fields")
                test[identity] = {}
                for label, active in (("primary", np.ones(len(age), dtype=bool)), ("birthday_sensitivity", ok)):
                    reported = recorded[label]
                    if reported["suppressed"]:
                        require(all(v is None for k, v in reported.items() if k != "suppressed"),
                                "Social context suppressed cell exposed a protected estimate or denominator")
                    value, reps = cell(eligible, bands, active, answered, positive, weights, standard, bridge)
                    compare(recorded[label], value, "social standardized proportion or suppression")
                    test[identity][label] = value, reps
                    withheld += value["suppressed"]
                    cells += 1
        comparisons += verify_comparisons(release["contrasts"], test, config["reference_groups"],
                                           config["practical_difference_pp"])
        food_pin = public[f"census_food_week{week}"]
        with ZipFile(pinned(public_raw, food_pin)) as archive:
            workbook = spreadsheet_cells(archive, {"US"})["US"]
        require(workbook["A4"] == "Total Population 18 Years and Older"
                and workbook["A8"] == "Total"
                and workbook["E6"] == "Sometimes not enough to eat" and workbook["F6"] == "Often not enough to eat",
                "Age context comparator population differs")
        published = sum(workbook[f"{col}8"] for col in "CDEF")
        official = (workbook["E8"] + workbook["F8"]) / published * 100
        complete = float(weights[food_answered, 0].sum())
        sample = float(weights[food_answered & food_insufficient, 0].sum()) / complete * 100
        difference = sample - official
        within = abs(difference) <= config["food_benchmark_pp"]
        compare(release["food_adults_18_plus_benchmark"], {
            "survey_pct": sample, "provider_pct": official, "survey_weighted_complete": complete,
            "provider_weighted_complete": float(published), "source_sha256": food_pin["sha256"],
            "difference_pp": difference, "within_tolerance": within,
        }, "social context adult food comparator")
        official_matches += within
    return {"descriptive_cells": cells, "withheld_cells": withheld, "contrast_checks": comparisons,
            "national_benchmark_agreements": official_matches, "waves": len(data["waves"])}
