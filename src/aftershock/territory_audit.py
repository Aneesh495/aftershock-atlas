"""Audit ambiguous reference years under current country and area identifiers."""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from datetime import date
from html import unescape
from pathlib import Path

from .history import validate_archive
from .io import ROOT, contained, digest, read_json, source_commit, write_json

CONFIG = ROOT / "configs/territory-audit-v10.json"
RESULT = ROOT / "data/results/territory-audit.json"
METRICS = ("population", "employment", "gdp", "school", "immunization", "mortality", "life_expectancy")
ERAS = ("before_change", "change_year", "after_change")


def attest_registry(config: dict) -> list[dict]:
    """Check the registered dates and codes without redistributing the UN page."""
    reference = config["reference"]
    result = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--location", "--compressed", "--proto", "=https",
         "--proto-redir", "=https", "--max-time", "30", "--max-filesize", "3000000", reference["url"]],
        check=True, capture_output=True, timeout=40,
    )
    import hashlib

    page = result.stdout
    if len(page) != reference["bytes"] or hashlib.sha256(page).hexdigest() != reference["sha256"]:
        raise ValueError("UN M49 page drifted from the registered geographic reference")
    text = " ".join(unescape(re.sub("<[^>]*>", " ", page.decode("utf-8-sig"))).split())
    notes = text[text.index("On 3 June 2006, Serbia and Montenegro"):]
    snippets = (
        r"On 3 June 2006, Serbia and Montenegro \(numerical code 891\) [^.]+\(numerical code 499\)[^.]+\(numerical code 688\)",
        r"Netherlands Antilles was changed to 530\. [^.]+ dissolved on 10 October 2010\.",
        r"On 9 July 2011, South Sudan \(numerical code 728\) became independent from Sudan \(numerical code 736\)",
    )
    if not all(re.search(pattern, notes) for pattern in snippets):
        raise ValueError("UN M49 notes no longer support the registered transitions")
    for item in config["transitions"]:
        for iso, code in item["successors"].items():
            if not re.search(rf"(?<![0-9]){code}\s+{iso}(?![A-Z])", text):
                raise ValueError("UN M49 current successor code does not match")
    return config["transitions"]


def checked(root: Path, pin: dict) -> Path:
    item = contained(root, pin["path"])
    if item.stat().st_size != pin["bytes"] or digest(item) != pin["sha256"]:
        raise ValueError(f"Territory audit input drifted: {pin['id']}")
    return item


def period(year: int, transition: str) -> str:
    start, stop = date(year, 1, 1), date(year, 12, 31)
    day = date.fromisoformat(transition)
    if day > stop:
        return "before_change"
    if day >= start:
        return "change_year"
    return "after_change"


def current_items(path: Path) -> list[dict]:
    response = read_json(path)
    meta, rows = response
    if meta["pages"] != 1 or meta["total"] != len(rows):
        raise ValueError("Incomplete current WDI measurement partition")
    return [{"region": entry["countryiso3code"], "year": int(entry["date"]), "raw_value": entry["value"]}
            for entry in rows if entry["countryiso3code"]]


def summarize(raw: list[dict], edition: str, metric: str, pins: dict, cfg: dict) -> list[dict]:
    registry = {iso: transition for transition in cfg["transitions"] for iso in transition["successors"]}
    last_available = cfg["last_year"] if edition == "current" else int(edition[:4])
    support, populated, future = Counter(), Counter(), Counter()
    unique = set()
    for row in raw:
        region, year = row["region"], row["year"]
        if region not in registry or not cfg["first_year"] <= year <= cfg["last_year"]:
            continue
        key = (region, year)
        if key in unique:
            raise ValueError("Duplicate successor region and reference year")
        unique.add(key)
        group = region, period(year, registry[region]["effective"])
        support[group] += 1
        if row["raw_value"] is None:
            continue
        if year > last_available:
            future[group] += 1
        else:
            populated[group] += 1
    rows = []
    for region, event in sorted(registry.items()):
        transition = int(event["effective"][:4])
        calendar_bound = {era: sum(
            period(year, event["effective"]) == era for year in range(cfg["first_year"], cfg["last_year"] + 1)
        ) for era in ERAS}
        for era in ERAS:
            key = region, era
            base = support[key]
            count = populated[key]
            future_rows = future[key]
            lower, upper = {"before_change": (cfg["first_year"], transition - 1),
                            "change_year": (transition, transition),
                            "after_change": (transition + 1, cfg["last_year"])}[era]
            rows.append({
                "region": region, "metric": metric, "edition": edition, "era": era, "first_year": lower,
                "last_year": upper, "observational_rows": base, "present": count, "future_values": future_rows,
                "reported_missing": base - count - future_rows, "absent_rows": calendar_bound[era] - base,
                "territory_basis_unverified": count if era != "after_change" else 0,
                "source_sha256": pins["sha256"], "transition_date": event["effective"],
            })
    return rows


def build_territory_audit() -> dict:
    config, history, plan, latest = [read_json(p) for p in (
        CONFIG, ROOT / "configs/history-inputs.json", ROOT / "configs/history-plan.json", ROOT / "configs/data-inputs.json"
    )]
    registry = attest_registry(config)
    rows = []
    for metric in METRICS:
        code = plan["series"][metric]
        for edition in plan["editions"]:
            pin = history[f"archive_{edition}_{metric}"]
            raw = validate_archive(read_json(checked(ROOT / "data/history/raw", pin)), edition, code)
            rows.extend(summarize(raw, edition, metric, pin, config))
        pin = latest[f"wb_{metric}"]
        rows.extend(summarize(current_items(checked(ROOT / "data/raw", pin)), "current", metric, pin, config))
    evidence = {
        "schema_version": 1, "source": source_commit(), "definitions_sha256": digest(CONFIG),
        "transition_registry": registry, "m49_reference": config["reference"],
        "evidence_limit": config["evidence_limit"], "rows": rows,
        "summary": {
            "registered_territories": sum(len(row["successors"]) for row in registry),
            "supplied_rows": sum(row["observational_rows"] for row in rows),
            "populated_rows_before_or_during_change": sum(row["territory_basis_unverified"] for row in rows),
            "future_values_excluded": sum(row["future_values"] for row in rows),
        },
    }
    write_json(RESULT, evidence)
    return evidence
