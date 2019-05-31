"""Estimate pandemic work disruptions from in-month CPS supplement linkages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile

from .acquire import Source, acquire_one
from .io import ROOT, digest, read_json, source_commit, write_json
from .resources import usage

CONFIG = ROOT / "configs/occupational-work-v6.json"
PINS = ROOT / "configs/occupation-inputs.json"
RAW = ROOT / "data/private-survey/labor"
RESULT = ROOT / "data/results/occupational-work.json"
OUTCOMES = ("telework", "unable_to_work")


def acquire_occupation() -> dict:
    sources = read_json(PINS)
    for key, pin in sources.items():
        source = Source(**{field: pin[field] for field in Source.__dataclass_fields__})
        receipt = acquire_one(source, RAW)
        if (receipt["sha256"], receipt["bytes"]) != (pin["sha256"], pin["bytes"]):
            raise ValueError(f"Occupational CPS source byte drift: {key}")
    return {"sources": len(sources)}


def exact_input(record: dict) -> Path:
    file = RAW / record["path"]
    if file.stat().st_size != record["bytes"] or digest(file) != record["sha256"]:
        raise ValueError(f"Occupational input fails its frozen identity: {record['id']}")
    return file


def record_fields(path: Path, origin: str, config: dict, kind: str) -> Iterable[dict[str, int]]:
    scope = config["sources"][origin]
    layout = config["fields"][kind]
    offsets = [(name, start - 1, end) for name, (start, end) in layout.items()]
    bound = 150_000_000 if kind == "basic" else 8_000_000
    expected = scope["record_count"]
    with ZipFile(path) as archive:
        contents = archive.infolist()
        if len(contents) != 1 or contents[0].filename != scope["archive_member"] or contents[0].file_size > bound:
            raise ValueError("CPS extract or basic member inventory")
        count = 0
        with archive.open(contents[0]) as stream:
            for record in stream:
                row = record.rstrip(b"\r\n")
                count += 1
                if len(row) not in scope["record_widths"] or count > expected:
                    raise ValueError("CPS record dimensions differ from frozen layout")
                yield {name: int(row[start:end].strip() or b"-1") for name, start, end in offsets}
        if count != expected:
            raise ValueError("CPS record count differs from frozen inventory")


def period(row: dict[str, int], month: str, short_year: bool) -> None:
    year, month_number = (int(v) for v in month.split("-"))
    if (row["year"], row["month"]) != (year % 100 if short_year else year, month_number):
        raise ValueError("CPS mix of reference months")


def survey_key(row: dict[str, int]) -> tuple[int, int]:
    return row["household_key"], row["person_key"]


@dataclass
class WeightedBinary:
    eligible_weight: int = 0
    valid_weight: int = 0
    yes_weight: int = 0
    composite_valid: int = 0
    composite_yes: int = 0
    respondent_count: int = 0
    affirmative_count: int = 0

    def add(self, response: int, weight: int, composite: int) -> None:
        self.eligible_weight += weight
        if response in (1, 2):
            self.valid_weight += weight
            self.composite_valid += composite
            self.respondent_count += 1
            if response == 1:
                self.yes_weight += weight
                self.composite_yes += composite
                self.affirmative_count += 1

    def public(self, config: dict) -> dict:
        minimum = config["minimum_both_outcomes"]
        if self.respondent_count < config["minimum_complete"] or not minimum <= self.affirmative_count <= self.respondent_count - minimum:
            return {"suppressed": True, "suppression_reason": "insufficient complete or binary outcome support",
                    "percent": None, "complete_respondents": None, "adult_worker_denominator": None}
        weight_scale = config["weight_divisor"]
        missing = self.eligible_weight - self.valid_weight
        return {
            "suppressed": False, "suppression_reason": None, "percent": 100 * self.yes_weight / self.valid_weight,
            "complete_respondents": self.respondent_count, "adult_worker_denominator": self.valid_weight / weight_scale,
            "weighted_affirmative_workers": self.yes_weight / weight_scale,
            "eligible_worker_population": self.eligible_weight / weight_scale,
            "weighted_item_missing_fraction": missing / self.eligible_weight,
            "missing_lower_percent": 100 * self.yes_weight / self.eligible_weight,
            "missing_upper_percent": 100 * (self.yes_weight + missing) / self.eligible_weight,
            "alternate_composite_weight_share_percent": (
                100 * self.composite_yes / self.composite_valid if self.composite_valid else None
            ),
        }


def group_index(config: dict) -> dict:
    return {
        ("national", "total"): "US civilian workers",
        **{("occupation", code): name for code, name in config["occupations"].items()},
        **{("industry", code): name for code, name in config["industries"].items()},
    }


def fit_month(month: str, config: dict, pins: dict) -> dict:
    suffix = month.replace("-", "")
    base_key, extract_key = f"cps_basic_{suffix}", f"cps_covid_{suffix}"
    base, extract = exact_input(pins[base_key]), exact_input(pins[extract_key])
    supplement = {}
    for row in record_fields(extract, extract_key, config, "covid"):
        period(row, month, short_year=True)
        key = survey_key(row)
        responses = row["telework"], row["unable_to_work"]
        if min(key) <= 0 or key in supplement or any(x not in {-1, 1, 2} for x in responses):
            raise ValueError("Invalid CPS extract key or response")
        supplement[key] = responses
    groups = group_index(config)
    scores = {(kind, code, outcome): WeightedBinary() for kind, code in groups for outcome in OUTCOMES}
    employed = interviewed = missing_link = absent_group = 0
    for row in record_fields(base, base_key, config, "basic"):
        period(row, month, short_year=False)
        key = survey_key(row)
        responses = supplement.pop(key, None)
        interviewed += responses is not None
        if row["person_type"] != 2 or row["age"] < 16 or row["employment"] not in {1, 2}:
            continue
        employed += 1
        primary, composite = row["supplement_weight"], row["composite_weight"]
        if primary <= 0 or composite < 0:
            raise ValueError("Invalid eligible CPS person weight")
        if responses is None:
            missing_link += 1
            responses = (-1, -1)
        classes = [("national", "total")]
        for kind in ("occupation", "industry"):
            identity = kind, str(row[kind])
            if identity in groups:
                classes.append(identity)
            else:
                absent_group += 1
        for kind, code in classes:
            for outcome, response in zip(OUTCOMES, responses, strict=True):
                scores[kind, code, outcome].add(response, primary, composite)
    if supplement or missing_link:
        raise ValueError("Unmatched eligible CPS rows or extract keys")
    rows = []
    for (kind, code, outcome), stats in scores.items():
        rows.append({"group_kind": kind, "group_code": code, "group": groups[kind, code],
                     "outcome": outcome, "month": month, **stats.public(config)})
    comparator = config["telework_comparators"][month]
    national = next(row for row in rows if row["group_kind"] == "national" and row["outcome"] == "telework")
    difference = national["percent"] - comparator["value"]
    return {"month": month, "source_sha256": {"basic": pins[base_key]["sha256"], "extract": pins[extract_key]["sha256"]},
            "linked_responses": interviewed, "eligible_workers": employed,
            "unassigned_classifications": absent_group, "rows": rows,
            "telework_comparator": {**comparator, "difference_pp": difference,
                                    "agrees": abs(difference) <= config["provider_agreement_pp"]}}


def comparisons(by_month: dict, config: dict) -> list[dict]:
    before, middle, latest = config["months"]
    base, end = ({(r["group_kind"], r["group_code"], r["outcome"]): r for r in by_month[t]["rows"]}
                 for t in (before, latest))
    middle_values = {(r["group_kind"], r["group_code"], r["outcome"]): r["percent"] for r in by_month[middle]["rows"]}
    output = []
    for key, start in base.items():
        finish = end[key]
        a, b = start["percent"], finish["percent"]
        gap = b - a if a is not None and b is not None else None
        output.append({
            "group_kind": key[0], "group_code": key[1], "group": start["group"], "outcome": key[2],
            "september_2020_percent": a, "september_2021_percent": middle_values[key], "september_2022_percent": b,
            "change_pp": gap, "meets_descriptive_change_threshold": abs(gap) >= config["practical_pp"] if gap is not None else None,
        })
    return output


def run_occupation() -> dict:
    usage(20_000_000)
    config, pins = read_json(CONFIG), read_json(PINS)
    for key, pin in pins.items():
        if key not in config["sources"]:
            exact_input(pin)
    series = {month: fit_month(month, config, pins) for month in config["months"]}
    data = {"schema_version": 1, "source": source_commit(), "definition_sha256": digest(CONFIG),
            "private_inputs_sha256": digest(PINS), "population": config["population"],
            "limitations": config["limitations"], "recall_days": config["recall_days"],
            "periods": series, "comparisons": comparisons(series, config)}
    write_json(RESULT, data)
    return data
