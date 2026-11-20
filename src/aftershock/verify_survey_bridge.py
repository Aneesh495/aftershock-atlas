"""Recompute Pulse estimates by matricizing the published person weights independently."""

from __future__ import annotations

import csv
import io
import math
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from .io import ROOT, digest, read_json
from .verification import require

NAMES = (
    "Symptoms of Anxiety Disorder", "Symptoms of Depressive Disorder",
    "Symptoms of Anxiety Disorder or Depressive Disorder",
)


def checked(raw: Path, pin: dict) -> Path:
    file = raw / pin["path"]
    require(file.stat().st_size == pin["bytes"] and digest(file) == pin["sha256"], "Survey bridge input mismatch")
    return file


def read_matrix(file: Path, week: str, count: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    main = f"pulse2021_puf_{week}.csv"
    replicates = f"pulse2021_repwgt_puf_{week}.csv"
    dictionary = f"pulse2021_data.dictionary_CSV_{week}.xlsx"
    items = np.empty((count, 4), dtype=np.int16)
    demographics = np.empty((count, 3), dtype=np.int16)
    weights = np.empty((count, 81))
    identities = {}
    fields = ("ANXIOUS", "WORRY", "INTEREST", "DOWN", "RHISPANIC", "RRACE", "INCOME")
    with ZipFile(file) as archive:
        members = archive.infolist()
        require(len(members) == 3 and set(archive.namelist()) == {main, replicates, dictionary}
                and sum(x.file_size for x in members) <= 250_000_000, "Pulse bridge archive inventory")
        with archive.open(main) as raw:
            rows = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            header = next(rows)
            loc = [header.index(name) for name in fields]
            ident, wave, weight = [header.index(name) for name in ("SCRAM", "WEEK", "PWEIGHT")]
            for index, row in enumerate(rows):
                key = row[ident]
                require(index < count and row[wave] == week and key and key not in identities,
                        "Survey wave or respondent inventory changed")
                identities[key] = index
                items[index] = [int(row[i]) for i in loc[:4]]
                demographics[index] = [int(row[i]) for i in loc[4:]]
                weights[index, 0] = float(row[weight])
        require(len(identities) == count, "Survey bridge population count changed")
        with archive.open(replicates) as raw:
            rows = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            header = next(rows)
            loc = [header.index(f"PWEIGHT{i}") for i in range(1, 81)]
            ident, wave = [header.index(name) for name in ("SCRAM", "WEEK")]
            for row in rows:
                key = row[ident]
                require(row[wave] == week and key in identities, "Public-use replicate pairing mismatch")
                weights[identities.pop(key), 1:] = [float(row[i]) for i in loc]
        require(not identities and np.isfinite(weights).all() and (weights >= 0).all()
                and (weights[:, 0] > 0).all(), "Survey bridge weight population changed")
    return demographics, items, weights


def memberships(config: dict, demographic: np.ndarray) -> dict:
    origin, race, incomes = demographic.T
    require(np.isin(origin, [1, 2]).all() and np.isin(race, [1, 2, 3, 4]).all()
            and np.isin(incomes, [-99, -88, *range(1, 9)]).all(), "Unregistered Pulse group code")
    groups = {("national", "United States"): np.full(len(origin), True)}
    for group, (o, r) in config["subgroups"]["race_origin"].items():
        groups["race_origin", group] = (origin == o) if r is None else (origin == o) & (race == r)
    for group, codes in config["subgroups"]["income"].items():
        groups["income", group] = np.isin(incomes, codes)
    return groups


def estimands(items: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    require(np.isin(items, [-99, -88, 1, 2, 3, 4]).all(), "Unregistered Pulse item code")
    observed = items > 0
    screen_anxiety = items[:, :2].sum(axis=1) > 4
    screen_depression = items[:, 2:].sum(axis=1) > 4
    return [
        (observed[:, :2].all(axis=1), screen_anxiety),
        (observed[:, 2:].all(axis=1), screen_depression),
        (observed.all(axis=1), screen_anxiety | screen_depression),
    ]


def source_table(file: Path, scopes: dict) -> dict:
    filter_rows = {(s["start"], s["end"], s["phase"]): k for k, s in scopes.items()}
    output = {}
    with file.open(encoding="utf-8-sig", newline="") as stream:
        for item in csv.DictReader(stream):
            if item["state"] != "United States" or item["group"] not in ("National Estimate", "By Race/Hispanic ethnicity"):
                continue
            period = (item["time_period_start_date"][:10], item["time_period_end_date"][:10], item["phase"])
            wave = filter_rows.get(period)
            if wave is not None and item["indicator"] in NAMES:
                key = (wave, item["subgroup"], item["indicator"])
                require(key not in output, "Duplicate CDC/NCHS comparator")
                output[key] = float(item["value"]) if item["value"] else None
    return output


def compare(actual: dict, expected: dict, reason: str) -> None:
    require(set(actual) == set(expected), f"Survey bridge publication or suppression fields changed: {reason}")
    for key, value in expected.items():
        if type(value) is float:
            require(type(actual[key]) in (float, int) and math.isclose(actual[key], value, rel_tol=1e-9, abs_tol=1e-7),
                    f"Survey bridge value changed: {reason}.{key}")
        else:
            require(type(actual[key]) is type(value) and actual[key] == value, f"Survey bridge value changed: {reason}.{key}")


def verify_survey_bridge(artifact: dict, comparator: Path, expected_source: str) -> dict:
    config_path = ROOT / "configs/survey-bridge-v5.json"
    pin_path = ROOT / "configs/survey-bridge-inputs.json"
    config, pins = read_json(config_path), read_json(pin_path)
    match = read_json(ROOT / "configs/data-inputs.json")["survey"]
    require(digest(comparator) == match["sha256"] and artifact["aggregate_comparator_sha256"] == match["sha256"],
            "Survey bridge comparator source changed")
    require(artifact["source"] == expected_source and artifact["definition_sha256"] == digest(config_path)
            and artifact["private_input_manifest_sha256"] == digest(pin_path), "Survey bridge source identity changed")
    require(artifact["comparability"] == config["wave_comparability"] and artifact["person_replicates"] == 80
            and artifact["variance_factor"] == .05 and artifact["population"] == config["population"]
            and artifact["context"] == config["context"], "Survey bridge estimand or comparability changed")
    require(set(artifact["waves"]) == set(config["waves"]), "Survey bridge wave inventory changed")
    published = source_table(comparator, config["waves"])
    raw = ROOT / "data/private-survey"
    expected_matches = expected_comparisons = expected_cells = 0
    for week, scope in config["waves"].items():
        wave = artifact["waves"][week]
        require(wave["wave"] == scope, "Survey bridge recall or response-rate contract changed")
        pin = pins[f"hps_week{week}"]
        require(wave["source_sha256"] == pin["sha256"], "Survey wave input identity changed")
        checked(raw, pins[f"hps_week{week}_design"])
        checked(raw, pins[f"hps_week{week}_questions"])
        demographics, items, weights = read_matrix(checked(raw, pin), week, scope["responses"])
        populations = memberships(config, demographics)
        outcomes = estimands(items)
        rows = {(r["group_kind"], r["group"], r["metric"]): r for r in wave["rows"]}
        program = {(kind, name, key) for kind, name in populations for key in NAMES}
        require(set(rows) == program and len(wave["rows"]) == len(program), "Survey bridge group/measure inventory changed")
        sensitivity = []
        for (kind, label), group in populations.items():
            weight_all = weights[group, 0].sum()
            for indicator, (answered, positive) in zip(NAMES, outcomes, strict=True):
                selected = group & answered
                cases = selected & positive
                total = int(selected.sum())
                yes = int(cases.sum())
                meta = {"group": label, "group_kind": kind, "metric": indicator, "week": int(week)}
                reason = None
                if total < 100 or min(yes, total - yes) < 10:
                    reason = "insufficient complete response"
                else:
                    final_weights = weights[selected]
                    denominator = final_weights.sum(axis=0)
                    numerator = weights[cases].sum(axis=0)
                    require((denominator > 0).all(), "Invalid Pulse replicate denominator")
                    ratios = numerator / denominator
                    estimate = float(ratios[0])
                    se = float(np.linalg.norm(ratios[1:] - estimate) / math.sqrt(20))
                    if se / estimate > .3:
                        reason = "unstable sampling estimate"
                if reason is not None:
                    want = {**meta, "suppressed": True, "suppression_reason": reason, "value": None,
                            "lower": None, "upper": None, "denominator": None}
                else:
                    official = published.get((week, label, indicator))
                    estimate_percent = estimate * 100
                    delta = estimate_percent - official if official is not None else None
                    agrees = abs(delta) <= .15 if delta is not None else None
                    expected_matches += agrees is True
                    expected_comparisons += delta is not None
                    margin = 1.959963984540054 * se
                    not_answered = weight_all - denominator[0]
                    want = {**meta, "suppressed": False, "suppression_reason": None, "value": estimate_percent,
                            "se": se * 100, "lower": 100 * max(0, estimate - margin),
                            "upper": 100 * min(1, estimate + margin), "complete_respondents": total,
                            "weighted_eligible_adults": float(weight_all), "denominator": float(denominator[0]),
                            "weighted_item_missing_fraction": float(not_answered / weight_all),
                            "item_missing_lower": float(100 * numerator[0] / weight_all),
                            "item_missing_upper": float(100 * (numerator[0] + not_answered) / weight_all),
                            "kish_effective_n": float(denominator[0] ** 2 / (final_weights[:, 0] ** 2).sum()),
                            "provider_value": official, "provider_difference_pp": delta, "provider_agreement": agrees}
                    if kind == "national":
                        mix = scope["weighted_unit_response_percent"] / 100
                        for shift in (-10, -5, 5, 10):
                            nonrespondents = float(np.clip(estimate_percent + shift, 0, 100))
                            sensitivity.append({"metric": indicator, "assumed_nonrespondent_shift_pp": shift,
                                                "scenario_percent": mix * estimate_percent + (1 - mix) * nonrespondents})
                compare(rows[kind, label, indicator], want, f"{week}.{kind}.{label}.{indicator}")
                expected_cells += 1
        require(len(wave["selection_sensitivity"]) == len(sensitivity), "Unit nonresponse sensitivity inventory changed")
        for result, expected in zip(wave["selection_sensitivity"], sensitivity, strict=True):
            compare(result, expected, f"{week} unit nonresponse")
    return {"waves": len(artifact["waves"]), "cell_checks": expected_cells,
            "provider_comparisons": expected_comparisons, "provider_point_matches": expected_matches}
