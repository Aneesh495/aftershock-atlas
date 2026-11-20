"""Build retrospective state surveillance aggregates from pinned reporting archives."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

from .acquire import Source, acquire_one
from .io import ROOT, digest, exclusive, read_json, source_commit, write_json
from .resources import usage

CONFIG = ROOT / "configs/surveillance-v5.json"
PINS = ROOT / "configs/surveillance-inputs.json"
RAW = ROOT / "data/state-surveillance/raw"
RESULT = ROOT / "data/results/state-surveillance.json"
ONE_WEEK = timedelta(days=7)
ADMISSIONS = "previous_day_admission_adult_covid_confirmed"
ICU = "staffed_icu_adult_patients_confirmed_covid"


def acquire_surveillance() -> dict:
    pins = read_json(PINS)
    with exclusive(RAW / ".acquire.lock"):
        for identity, pin in pins.items():
            spec = Source(**{k: pin[k] for k in Source.__dataclass_fields__})
            receipt = acquire_one(spec, RAW)
            if receipt["sha256"] != pin["sha256"] or receipt["bytes"] != pin["bytes"]:
                raise ValueError(f"Frozen state surveillance input changed: {identity}")
        write_json(RAW / "index.json", pins)
    return {"sources": len(pins)}


def source_path(raw: Path, record: dict) -> Path:
    path = raw / record["path"]
    if path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
        raise ValueError(f"Frozen state surveillance source mismatch: {record['id']}")
    return path


def exact_date(value: str) -> date:
    day = date.fromisoformat(value[:10])
    if value != day.isoformat() and value not in {
        f"{day.isoformat()}T00:00:00", f"{day.isoformat()}T00:00:00.000",
    }:
        raise ValueError("Expected a state surveillance date without time-of-day")
    return day


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def number(raw: str, *, fraction: bool = False) -> int | float | None:
    if raw == "":
        return None
    value = float(raw) if fraction else int(raw)
    if not math.isfinite(value):
        raise ValueError("Nonfinite state surveillance value")
    return value


def level(raw: str) -> int | None:
    value = number(raw)
    return value if value is not None and value >= 0 else None


def state_records(kind: str, config: dict, pins: dict, raw: Path) -> Iterable[tuple[str, date, dict]]:
    rule = config["fields"][kind]
    totals = read_json(source_path(raw, pins[f"v5_{kind}_count"]))
    if len(totals) != 1:
        raise ValueError("Unexpected surveillance count response")
    window = totals[0]
    expected = int(window["row_count"])
    if not 0 < expected < rule["limit"]:
        raise ValueError("Source count is empty or the request was truncated")
    earliest = date.max
    latest = date.min
    previous = None
    count = 0
    file = source_path(raw, pins[f"v5_{kind}_rows"])
    with file.open(newline="") as stream:
        rows = csv.DictReader(stream)
        if rows.fieldnames != rule["columns"]:
            raise ValueError(f"State surveillance source columns changed: {kind}")
        for row in rows:
            if None in row or None in row.values():
                raise ValueError("Invalid source record width")
            count += 1
            state = row[rule["jurisdiction"]]
            day = exact_date(row["date"])
            state_codes = config["state_fips"]
            if state not in state_codes or not rule["first"] <= day.isoformat() <= rule["last"]:
                raise ValueError("Source includes an unregistered date or jurisdiction")
            if kind == "testing":
                if row["state_fips"].zfill(2) != state_codes[state]:
                    raise ValueError("PCR state and FIPS code disagree")
                if row["overall_outcome"] not in config["test_outcomes"]:
                    raise ValueError("Unregistered PCR result category")
            order = (state, day, row.get("overall_outcome", ""))
            if previous and order <= previous:
                raise ValueError("Duplicate or unordered jurisdiction-date identity")
            previous = order
            earliest = min(day, earliest)
            latest = max(day, latest)
            yield state, day, row
    if (
        count != expected or earliest != exact_date(window["earliest"])
        or latest != exact_date(window["latest"])
    ):
        raise ValueError(f"State surveillance data disagree with independent provider query: {kind}")


def group_reports(rows: Iterable[tuple[str, date, dict]]) -> dict:
    grouped = defaultdict(list)
    for state, day, row in rows:
        grouped[state, monday(day)].append((day, row))
    return grouped


def flow(values: list[int]) -> dict:
    return {
        "days": len(values),
        "weekly_total": sum(values) if len(values) == 7 else None,
        "reported_total": sum(values) if values else None,
    }


def stock(values: list[int]) -> dict:
    return {
        "days": len(values),
        "weekly_mean": sum(values) / 7 if len(values) == 7 else None,
        "reported_mean": sum(values) / len(values) if values else None,
    }


def matched_beds(rows: list[tuple[date, dict]], prefix: str) -> dict:
    valid = []
    inconsistent = 0
    for _, row in rows:
        n, d, c = (level(row[f"{prefix}_{item}"]) for item in ("numerator", "denominator", "coverage"))
        if n is not None and d is not None and c is not None and 0 <= n <= d and d > 0 and c > 0:
            valid.append((n, d, c))
        elif n is not None and d is not None and n > d:
            inconsistent += 1
    numerators, denominators, coverage = zip(*valid) if valid else ((), (), ())
    denominator = sum(denominators)
    return {
        "paired_days": len(valid),
        "occupied_bed_days": sum(numerators) if valid else None,
        "staffed_bed_days": denominator if valid else None,
        "minimum_contributors": min(coverage, default=None),
        "over_capacity_days": inconsistent,
        "weekly_percent": 100 * sum(numerators) / denominator if len(valid) == 7 else None,
    }


def hospital_week(rows: list[tuple[date, dict]]) -> dict:
    admissions = [value for _, row in rows if (value := level(row[ADMISSIONS])) is not None]
    reported_icu = []
    contributors = []
    for _, row in rows:
        val, count = level(row[ICU]), level(row[f"{ICU}_coverage"])
        if val is not None and count:
            reported_icu.append(val)
            contributors.append(count)
    icu = {**stock(reported_icu), "minimum_contributors": min(contributors, default=None)}
    return {
        "reports": len(rows),
        "confirmed_adult_admissions": flow(admissions),
        "confirmed_adult_icu_patients": icu,
        "all_cause_adult_icu_occupancy": matched_beds(rows, "adult_icu_bed_utilization"),
        "confirmed_or_suspected_adult_icu_occupancy": matched_beds(rows, "adult_icu_bed_covid_utilization"),
    }


def pcr_week(rows: list[tuple[date, dict]], categories: list[str]) -> dict:
    outcomes: dict[str, list[int]] = {c: [] for c in categories}
    cumulative: dict[str, dict] = {}
    corrections = 0
    for day, row in rows:
        name = row["overall_outcome"]
        value = number(row["new_results_reported"])
        if value is not None:
            outcomes[name].append(value)
            corrections += value < 0
        total = level(row["total_results_reported"])
        if total is not None:
            cumulative[name.lower()] = {"date": day.isoformat(), "count": total}
    pos, neg = outcomes["Positive"], outcomes["Negative"]
    denominator = sum(pos) + sum(neg)
    complete = len(pos) == len(neg) == 7
    return {
        "reports": len({day for day, _ in rows}),
        **{c.lower(): flow(v) for c, v in outcomes.items()},
        "latest_cumulative_results": cumulative,
        "negative_result_corrections": corrections,
        "determinate_results": denominator if complete and not corrections else None,
        "weekly_positivity_percent": 100 * sum(pos) / denominator if complete and not corrections and denominator > 0 else None,
    }


def vaccination_reports(rows: Iterable[tuple[str, date, dict]], cap_values: list[float]) -> dict:
    grouped = defaultdict(list)
    previous: dict[str, tuple[date, int | None]] = {}
    for state, day, row in rows:
        count = level(row["series_complete_yes"])
        doses = level(row["administered"])
        percent = number(row["series_complete_pop_pct"], fraction=True)
        if percent is not None and not 0 <= percent <= 100:
            raise ValueError("Vaccination percent outside its registered scale")
        earlier, baseline = previous.get(state, (None, None))
        change = count - baseline if count is not None and baseline is not None else None
        grouped[state, monday(day)].append({
            "report_date": day.isoformat(),
            "previous_report_date": earlier.isoformat() if earlier else None,
            "days_since_previous_report": (day - earlier).days if earlier else None,
            "resident_primary_series_complete": count,
            "provider_coverage_percent": percent,
            "matches_documented_cap": percent in cap_values,
            "administered_doses_in_jurisdiction": doses,
            "signed_primary_series_update": change,
        })
        previous[state] = day, count
    return grouped


def vaccination_week(rows: list[dict]) -> dict:
    decreases = [
        {"report_date": row["report_date"], "previous_report_date": row["previous_report_date"],
         "signed_primary_series_update": row["signed_primary_series_update"]}
        for row in rows
        if row["signed_primary_series_update"] is not None and row["signed_primary_series_update"] < 0
    ]
    return {
        "reports": len(rows),
        "latest_report": rows[-1] if rows else None,
        "negative_completion_updates": len(decreases),
        "completion_corrections": decreases,
    }


def build_surveillance(raw: Path = RAW, output: Path = RESULT) -> dict:
    usage(70_000_000)
    config = read_json(CONFIG)
    pins = read_json(PINS)
    grouped = {
        "hospital": group_reports(state_records("hospital", config, pins, raw)),
        "testing": group_reports(state_records("testing", config, pins, raw)),
        "vaccination": vaccination_reports(state_records("vaccination", config, pins, raw),
                                          config["cdc_published_cap_values"]),
    }
    states: dict[str, dict] = {state: {} for state in config["state_fips"]}
    summary = {}
    for kind, rule in config["fields"].items():
        first, last = date.fromisoformat(rule["first"]), date.fromisoformat(rule["last"])
        start = monday(first)
        count = (monday(last) - start).days // 7 + 1
        supports = {"weeks": 0, "with_reports": 0, "with_seven_report_dates": 0}
        for state in states:
            weeks = []
            for i in range(count):
                week = start + i * ONE_WEEK
                records = grouped[kind].get((state, week), [])
                if kind == "hospital":
                    result = hospital_week(records)
                elif kind == "testing":
                    result = pcr_week(records, config["test_outcomes"])
                else:
                    result = vaccination_week(records)
                supports["weeks"] += 1
                supports["with_reports"] += result["reports"] > 0
                supports["with_seven_report_dates"] += result["reports"] == 7
                weeks.append({"week_start": week.isoformat(), **result})
            states[state][kind] = weeks
        summary[kind] = supports
    artifact = {
        "schema_version": 1,
        "source": source_commit(),
        "definition_sha256": digest(CONFIG),
        "pins_sha256": digest(PINS),
        "registry": config["fields"],
        "inputs": {k: {"bytes": v["bytes"], "sha256": v["sha256"]} for k, v in pins.items()},
        "summary": summary,
        "states": states,
    }
    write_json(output, artifact)
    return artifact
