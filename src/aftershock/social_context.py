"""Age-standardized adult survey estimates with design-based subgroup contrasts."""
from __future__ import annotations

import math
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from openpyxl import load_workbook
from scipy.special import erfc

from .acquire import Source, acquire_one
from .io import ROOT, contained, digest, read_json, source_commit, write_json
from .statistics import bh_adjust
from .survey_bridge import bridge_scores, codes
from .survey_design import archive_rows

CONFIG = ROOT / "configs/social-context-v8.json"
PINS = ROOT / "configs/social-context-inputs.json"
BRIDGE = ROOT / "configs/survey-bridge-v5.json"
PRIVATE_PINS = ROOT / "configs/survey-bridge-inputs.json"
RAW = ROOT / "data/chronology/raw"
RESULT = ROOT / "data/results/social-context.json"
METRICS = ("food_insufficiency", "mental_health_screen")
MODES = ("primary", "birthday_sensitivity")
Z = 1.959963984540054


def acquire_context() -> dict:
    for pin in read_json(PINS).values():
        spec = Source(**{k: pin[k] for k in Source.__dataclass_fields__})
        result = acquire_one(spec, RAW)
        if result["sha256"] != pin["sha256"] or result["bytes"] != pin["bytes"]:
            raise ValueError(f"Social context input changed: {spec.id}")
    return {"public_sources": len(read_json(PINS))}


def checked(root: Path, pin: dict) -> Path:
    target = contained(root, pin["path"])
    if target.stat().st_size != pin["bytes"] or digest(target) != pin["sha256"]:
        raise ValueError(f"Social context input identity differs: {pin['id']}")
    return target


def food_reference(path: Path, week: str) -> tuple[float, float]:
    with ZipFile(path) as archive:
        if len(archive.infolist()) > 240 or sum(member.file_size for member in archive.infolist()) > 25_000_000:
            raise ValueError("Food workbook exceeds analysis bounds")
    with path.open("rb") as raw:
        workbook = load_workbook(raw, read_only=True, data_only=True)
        try:
            sheet = workbook["US"]
            if sheet["A2"].value != f"Source: U.S. Census Bureau Household Pulse Survey, Week {week}." or (
                sheet["A4"].value != "Total Population 18 Years and Older"
                or sheet["A8"].value != "Total"
                or [sheet[f"{c}6"].value for c in "EFG"] != [
                    "Sometimes not enough to eat", "Often not enough to eat", "Did not report"
                ]
            ):
                raise ValueError("Food workbook does not describe the frozen comparison population")
            enough, enough_other, sometimes, often = (sheet[f"{c}8"].value for c in "CDEF")
            return sometimes + often, round(enough + enough_other + sometimes + often, 8)
        finally:
            workbook.close()


def standard_vector(cfg: dict) -> np.ndarray:
    masses = np.asarray([sum(b["standard_components"].values()) for b in cfg["age_bands"]], dtype=float)
    return masses / masses.sum()


def group_definitions(cfg: dict, bridge: dict) -> list[tuple[str, str, list]]:
    return [("national", "United States", []), *(
        (family, label, codes) for family, groups in (
            ("race_origin", bridge["subgroups"]["race_origin"]), ("income", cfg["income"]), ("tenure", cfg["tenure"])
        ) for label, codes in groups.items()
    )]


def score_record(row: dict, cfg: dict, bridge: dict, groups: list) -> tuple:
    origin, race, income = codes(row)
    age, tenure, food = (int(row[key]) for key in ("TBIRTH_YEAR", "TENURE", "CURFOODSUF"))
    age = cfg["age_year"] - age
    if not 18 <= age <= 88 or tenure not in {-99, -88, 1, 2, 3, 4} or food not in {-99, -88, 1, 2, 3, 4}:
        raise ValueError("Unregistered survey age, food or tenure code")
    band = next((i for i, b in enumerate(cfg["age_bands"]) if b["lower"] <= age <= b["upper"]), None)
    certain = band is not None and age != cfg["age_bands"][band]["lower"]
    selected = [0]
    categories = {"income": income, "tenure": tenure}
    for i, (family, _, values) in enumerate(groups[1:], 1):
        eligible = [origin, race if origin == 1 else None] == values if family == "race_origin" else categories[family] in values
        if eligible:
            selected.append(i)
    symptom = bridge_scores(row, bridge)[-1]
    return band, certain, selected, (float(food >= 3) if food > 0 else math.nan, symptom)


def collect(path: Path, week: str, cfg: dict, bridge: dict, groups: list) -> tuple:
    main, replicate, dictionary = (f"pulse2021_{stem}_{week}.{fmt}" for stem, fmt in (
        ("puf", "csv"), ("repwgt_puf", "csv"), ("data.dictionary_CSV", "xlsx")
    ))
    shape = (2, len(groups), len(METRICS), len(cfg["age_bands"]))
    eligible = np.zeros(shape[:2] + shape[3:])
    complete = np.zeros(shape, dtype=int)
    positive = np.zeros_like(complete)
    denom, numer = np.zeros((*shape, 81)), np.zeros((*shape, 81))
    all_adult_food = np.zeros(2)
    records = {}
    with ZipFile(path) as archive:
        if set(archive.namelist()) != {main, replicate, dictionary} or len(archive.infolist()) != 3 or (
            sum(member.file_size for member in archive.infolist()) > 250_000_000
        ):
            raise ValueError("Age context wave archive inventory differs")
        for row in archive_rows(archive, main):
            key, full = row["SCRAM"], float(row["PWEIGHT"])
            if not key or key in records or row["WEEK"] != week or not math.isfinite(full) or full <= 0:
                raise ValueError("Duplicate survey adult, different wave or invalid adult person weight")
            band, certain, members, scores = score_record(row, cfg, bridge, groups)
            if math.isfinite(scores[0]):
                all_adult_food += full * np.asarray([1, scores[0]])
            records[key] = full, band, certain, members, scores
        if len(records) != bridge["waves"][week]["responses"]:
            raise ValueError("Survey context wave sample inventory changed")
        for row in archive_rows(archive, replicate):
            key = row["SCRAM"]
            if row["WEEK"] != week or key not in records:
                raise ValueError("Duplicate, unmatched or wrong-wave replication record")
            full, band, certain, members, scores = records.pop(key)
            weights = np.array([full, *(float(row[f"PWEIGHT{i}"]) for i in range(1, 81))])
            if not np.isfinite(weights).all() or (weights < 0).any():
                raise ValueError("Survey context invalid person replicate weights")
            if band is None:
                continue
            for mode in range(2 if certain else 1):
                for member in members:
                    eligible[mode, member, band] += full
                    for outcome, score in enumerate(scores):
                        if not math.isfinite(score):
                            continue
                        key = mode, member, outcome, band
                        denom[key] += weights
                        numer[key] += weights * score
                        complete[key] += 1
                        positive[key] += int(score)
        if records:
            raise ValueError("Some survey adults lack a matched replicate record")
    return eligible, denom, numer, complete, positive, all_adult_food


def suppression() -> dict:
    return {"suppressed": True, "adjusted_pct": None, "crude_pct": None, "se_pp": None,
            "lower": None, "upper": None, "complete_adults": None, "weighted_complete": None,
            "item_missing_pct": None, "item_missing_lower": None, "item_missing_upper": None}


def usesafe(yes: np.ndarray, total: np.ndarray, bridge: dict) -> bool:
    return bool((total >= bridge["minimum_complete"]).all()
                and (np.minimum(yes, total - yes) >= bridge["minimum_in_each_outcome"]).all())


def estimate(eligible, denom, numer, total, yes, weights, bridge) -> tuple:
    if not usesafe(yes, total, bridge) or (denom <= 0).any():
        return suppression(), None
    estimates = weights @ (numer / denom)
    value = float(estimates[0])
    se = float(np.sqrt(bridge["variance_factor"] * np.square(estimates[1:] - value).sum()))
    if not np.isfinite(estimates).all() or not value > 0 or se / value > bridge["maximum_relative_standard_error"]:
        return suppression(), None
    full = denom[:, 0]
    cases = numer[:, 0]
    missing = np.maximum(0, eligible - full)
    return {
        "suppressed": False, "adjusted_pct": value * 100, "crude_pct": float(cases.sum() / full.sum() * 100),
        "se_pp": se * 100, "lower": max(0, value - Z * se) * 100, "upper": min(1, value + Z * se) * 100,
        "complete_adults": int(total.sum()), "weighted_complete": float(full.sum()),
        "item_missing_pct": float(missing.sum() / eligible.sum() * 100),
        "item_missing_lower": float(weights @ (cases / eligible) * 100),
        "item_missing_upper": float(weights @ ((cases + missing) / eligible) * 100),
    }, estimates


def compare_groups(rows: dict, replicates: dict, cfg: dict, bridge: dict) -> list[dict]:
    contrasts = []
    for metric in METRICS:
        primary = []
        for (family, label, endpoint), values in rows.items():
            baseline = cfg["reference_groups"].get(family)
            if baseline is None or label == baseline or endpoint != metric:
                continue
            comparison = []
            for mode_i, mode in enumerate(MODES):
                a, b = replicates[(family, label, metric)][mode_i], replicates[(family, baseline, metric)][mode_i]
                fields = {"mode": mode, "difference_pp": None, "se_pp": None, "lower": None, "upper": None,
                          "crude_difference_pp": None, "large_difference": None, "p": None, "q": None}
                if a is not None and b is not None:
                    delta = 100 * (a - b)
                    point = float(delta[0])
                    spread = float(np.sqrt(bridge["variance_factor"] * np.square(delta[1:] - point).sum()))
                    crude = values[mode]["crude_pct"] - rows[(family, baseline, metric)][mode]["crude_pct"]
                    fields.update(difference_pp=point, se_pp=spread, lower=point - Z * spread, upper=point + Z * spread,
                                  crude_difference_pp=crude, large_difference=abs(point) >= cfg["practical_difference_pp"],
                                  p=float(erfc(abs(point) / (math.sqrt(2) * spread))) if spread > 0 else None)
                comparison.append(fields)
            if comparison[0]["p"] is not None:
                primary.append(comparison[0])
            contrasts.append({"group_kind": family, "group": label, "reference": baseline,
                              "metric": metric, "estimates": comparison})
        for row, q in zip(primary, bh_adjust([r["p"] for r in primary]), strict=True):
            row["q"] = q
    return contrasts


def build_context() -> dict:
    cfg, bridge, pins, private = map(read_json, (CONFIG, BRIDGE, PINS, PRIVATE_PINS))
    groups, standard = group_definitions(cfg, bridge), standard_vector(cfg)
    source_standard = checked(RAW, pins["nchs_2000_standard"])
    text = source_standard.read_text(encoding="utf-8")
    if any(f"<td>{count:,}</td>" not in text for b in cfg["age_bands"] for count in b["standard_components"].values()):
        raise ValueError("NCHS published standard-million counts changed")
    result = {
        "schema_version": 1, "source": source_commit(), "config_sha256": digest(CONFIG),
        "inputs_sha256": digest(PINS), "private_inputs_sha256": digest(PRIVATE_PINS),
        "age_standard": dict(zip((b["label"] for b in cfg["age_bands"]), standard.tolist(), strict=True)),
        "metric_labels": cfg["metrics"], "comparison_scope": cfg["comparison_scope"],
        "nonresponse_scope": cfg["nonresponse_scope"], "age_sensitivity": cfg["age_sensitivity"],
        "standard_source": cfg["standard_source"], "waves": {},
    }
    for week, scope in bridge["waves"].items():
        archive = checked(ROOT / "data/private-survey", private[f"hps_week{week}"])
        eligible, denom, numer, total, yes, national = collect(archive, week, cfg, bridge, groups)
        rows, replicas = {}, {}
        for i, (family, label, _) in enumerate(groups):
            for j, metric in enumerate(METRICS):
                name = family, label, metric
                rows[name], replicas[name] = {}, []
                for mode, field in enumerate(MODES):
                    index = mode, i, j
                    estimate_data, draw = estimate(eligible[mode, i], denom[index], numer[index], total[index],
                                                   yes[index], standard, bridge)
                    rows[name][field] = estimate_data
                    replicas[name].append(draw)
        source = pins[f"census_food_week{week}"]
        official_positive, official_weight = food_reference(checked(RAW, source), week)
        computed = float(national[1] / national[0] * 100)
        published = official_positive / official_weight * 100
        result["waves"][week] = {
            "wave": scope, "source_sha256": private[f"hps_week{week}"]["sha256"],
            "food_adults_18_plus_benchmark": {
                "survey_pct": computed, "provider_pct": published, "survey_weighted_complete": float(national[0]),
                "provider_weighted_complete": official_weight, "source_sha256": source["sha256"],
                "difference_pp": computed - published, "within_tolerance": abs(computed - published) <= cfg["food_benchmark_pp"],
            },
            "rows": [{"group_kind": f, "group": name, "metric": endpoint, **estimate_data}
                     for (f, name, endpoint), estimate_data in rows.items()],
            "contrasts": compare_groups(rows, replicas, cfg, bridge),
        }
    write_json(RESULT, result)
    return result
