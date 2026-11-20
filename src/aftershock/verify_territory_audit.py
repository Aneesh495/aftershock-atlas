"""Count historical identity risk directly in original WDI data dimensions."""
from __future__ import annotations

from collections import Counter

from .io import ROOT, contained, digest, read_json
from .verification import require


def verify_territory(data: dict, source: str) -> dict:
    config_file = ROOT / "configs/territory-audit-v10.json"
    config = read_json(config_file)
    archive_plan = read_json(ROOT / "configs/history-plan.json")
    archives = read_json(ROOT / "configs/history-inputs.json")
    current = read_json(ROOT / "configs/data-inputs.json")
    regions = {region: event["effective"] for event in config["transitions"] for region in event["successors"]}
    require(data["schema_version"] == 1 and data["source"] == source
            and data["definitions_sha256"] == digest(config_file)
            and data["transition_registry"] == config["transitions"]
            and data["m49_reference"] == config["reference"] and data["evidence_limit"] == config["evidence_limit"],
            "Territory transition codes, dates or evidence basis changed")
    expected = {(edition, metric, region, era)
                for edition in [*archive_plan["editions"], "current"] for metric in archive_plan["series"]
                for region in regions for era in ("before_change", "change_year", "after_change")}
    results = {(row["edition"], row["metric"], row["region"], row["era"]): row for row in data["rows"]}
    require(set(results) == expected and len(results) == len(data["rows"]), "Territory audit scope missing or duplicated")
    seen, suspect, future_rows = 0, 0, 0
    for edition in [*archive_plan["editions"], "current"]:
        for metric, metric_code in archive_plan["series"].items():
            pin = current[f"wb_{metric}"] if edition == "current" else archives[f"archive_{edition}_{metric}"]
            raw = ROOT / ("data/raw" if edition == "current" else "data/history/raw")
            path = contained(raw, pin["path"])
            require(digest(path) == pin["sha256"] and path.stat().st_size == pin["bytes"], "Territory audit raw measurement input differs")
            content = read_json(path)
            cells = {}
            if edition == "current":
                header, records = content
                require(header["pages"] == 1 and header["total"] == len(records), "Territory current input truncated")
                for item in records:
                    region, time = item["countryiso3code"], int(item["date"])
                    if region in regions:
                        require((region, time) not in cells, "Territory WDI current record duplicated")
                        cells[region, time] = item["value"]
            else:
                records = content["source"]["data"]
                require(content["pages"] == 1 and content["total"] == len(records), "Territory archive input truncated")
                for item in records:
                    dimensions = {field["concept"]: field["id"] for field in item["variable"]}
                    region, time = dimensions["Country"], int(dimensions["Time"][2:])
                    require(dimensions["Version"] == edition and dimensions["Series"] == metric_code,
                            "Territory audit source vintage or metric changed")
                    if region in regions:
                        require((region, time) not in cells, "Territory WDI archive record duplicated")
                        cells[region, time] = item["value"]
            since = config["first_year"]
            through = config["last_year"]
            for region, transition in regions.items():
                yr = int(transition[:4])
                windows = {"before_change": range(since, yr), "change_year": range(yr, yr + 1),
                           "after_change": range(yr + 1, through + 1)}
                for era, interval in windows.items():
                    availability = Counter()
                    for year in interval:
                        key = (region, year)
                        if key not in cells:
                            availability["absent_rows"] += 1
                        elif cells[key] is None:
                            availability["reported_missing"] += 1
                        elif edition != "current" and year > int(edition[:4]):
                            availability["future_values"] += 1
                        else:
                            availability["present"] += 1
                    available = len(interval) - availability["absent_rows"]
                    risk = 0 if era == "after_change" else availability["present"]
                    stamp = results[edition, metric, region, era]
                    require(stamp == {
                        "edition": edition, "metric": metric, "region": region, "era": era,
                        "first_year": interval.start, "last_year": interval.stop - 1, "observational_rows": available,
                        **{k: availability[k] for k in ("absent_rows", "reported_missing", "future_values", "present")},
                        "territory_basis_unverified": risk, "transition_date": transition, "source_sha256": pin["sha256"],
                    }, "Territory support or predecessor comparability altered")
                    seen += available
                    suspect += risk
                    future_rows += availability["future_values"]
    summary = {"registered_territories": len(regions), "supplied_rows": seen,
               "populated_rows_before_or_during_change": suspect, "future_values_excluded": future_rows}
    require(data["summary"] == summary, "Territory audit totals differ")
    return {"scoped_cells": len(expected), **summary}
