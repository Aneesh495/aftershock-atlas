"""Validate the archived interactive walkthrough and the downloaded CSV evidence."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

from .io import ROOT, contained, digest, read_json
from .verification import require
from .verify_measurement import same

WALKTHROUGH = ROOT / "docs/media/hosted-v9"
REFERENCE = ROOT / "docs/CHRONOLOGY_AND_CALIBRATION_RECEIPT_V9.json"
EXPORTS = {
    "employment_observed": 52, "mortality_trajectory": 64, "labor_sector": 27,
    "labor_occupation": 13, "uk_gdp_revisions": 18, "ct_crosswalk": 3,
    "uk_gdp_forecast": 56, "survey_context": 3,
}


def public_rows(name: str, index: dict) -> list | dict:
    filename = f"{name}.json"
    raw = subprocess.check_output(
        ["git", "show", f"HEAD:client/public/data/{filename}"], cwd=ROOT, timeout=15)
    require(hashlib.sha256(raw).hexdigest() == index["files"][filename], "Browser record canonical data checksum mismatch")
    return json.loads(raw)


def recorded_downloads(walkthrough: Path, record: dict) -> dict:
    require(set(record["exports"]) == set(EXPORTS), "Required browser walkthrough export is missing")
    exports = {}
    for identity, size in EXPORTS.items():
        spec = record["exports"][identity]
        filename = f"{identity}.csv"
        require(spec["path"] == f"docs/media/hosted-v9/{filename}", "Walkthrough download path substitution")
        path = contained(walkthrough, filename)
        require(digest(path) == spec["sha256"] and path.stat().st_size <= 100_000, "Browser export data checksum differs")
        with path.open(encoding="utf-8", newline="") as stream:
            items = list(csv.DictReader(stream))
        require(len(items) == size == spec["rows"] and all(None not in row for row in items),
                "Browser export row count or schema altered")
        exports[identity] = items
    return exports


def number(row: dict, field: str) -> float | None:
    entry = row[field]
    return float(entry) if entry else None


def verify_trajectories(exports: dict, index: dict) -> int:
    countries = {"USA", "GBR"}
    for file, endpoint in (("employment_observed", "employment"), ("mortality_trajectory", "mortality")):
        observed = [row for row in exports[file] if row["kind"] != "predictive_no_shock"]
        observed_values = {(row["region"], int(row["yr"])): row for row in observed}
        truth = {(row["region"], row["yr"]): row["value"] for row in public_rows(endpoint, index)
                 if row["region"] in countries}
        require(len(observed) == len(observed_values) == len(truth) and set(observed_values) == set(truth),
                "Browser comparison leaked or lost an observed population")
        for key, row in observed_values.items():
            require(row["source_panel"] == index["panel_sha256"], "Browser comparison source panel differs")
            same(number(row,"value"), truth[key], "Browser observed comparison disagrees with the frozen data")
    projected = [row for row in exports["mortality_trajectory"] if row["kind"] == "predictive_no_shock"]
    choices = {(r["region"], r["year"]): r for r in public_rows("scenarios", index)
               if r["region"] in countries and r["metric"] == "mortality" and r["year"] >= 2020}
    require(len(projected) == len(choices) == 12, "Browser projection export omits the active forecast population")
    for row in projected:
        identity = row["region"], int(row["yr"])
        require(identity in choices and row["scenario_sha256"] == index["files"]["scenarios.json"],
                "Browser projection is detached from the exact model partition")
        for actual, expected in (("display_value", "scenario"), ("lower", "lower"), ("upper", "upper")):
            same(number(row, actual), choices[identity][expected], "Browser no-shock trajectory or interval was substituted")
    require(len({(r["region"], r["yr"]) for r in projected}) == len(choices), "Browser projected key duplicated")
    return len(projected)


def verify_walkthrough(walkthrough: Path, reference: Path = REFERENCE) -> dict:
    record = read_json(walkthrough / "checks.json")
    index_file = walkthrough / "data-index.json"
    research = read_json(reference)
    index = read_json(index_file)
    require(record["schema_version"] == 1 and digest(index_file) == record["data_index_sha256"]
            and index["published_extensions"]["source"] == record["extension_scientific_source"] == research["source"]
            and index["published_extensions"]["partitions"] == research["partitions"],
            "Browser walkthrough data identities differ from the verified research release")
    require(record["served_url"] == "https://aneesh495.github.io/aftershock-atlas/"
            and record["pages_run"] == "https://github.com/Aneesh495/aftershock-atlas/actions/runs/44826149286"
            and record["pages_source"] == "bac72de3e8e07d9b08adff134ab6ba53bf1b465c",
            "Browser proof is not bound to the checked public deployment")
    viewed = record["core_checks"]
    require(viewed["countries"] == ["USA", "GBR"] and viewed["periods"] == [2019, 2020, 2023]
            and viewed["scenario_off_rows"] == 52 and viewed["scenario_on_rows"] == 64 and viewed["projected_rows"] == 12
            and viewed["causal_study"] == "S06" and viewed["causal_late_cohort_supported"] is False
            and viewed["subnational_selection"] == ["California", "Florida"]
            and viewed["biological_groups"] == ["host associations with shared sample", "separate archived weighted viral lineages"],
            "The integrated browser path is incomplete")
    controls = record["extension_checks"]
    require(controls["persisted_selection"] is True and controls["console_errors"] == 0
            and controls["age_sensitivity"] is True and controls["selected_survey_wave"] == 33
            and controls["mobile_scroll_widths"] == [[320, 320], [390, 390], [1280, 1280]],
            "Browser input persistence or responsive viewport check is missing")
    downloads = recorded_downloads(walkthrough, record)
    projections = verify_trajectories(downloads, index)
    for name, rows in downloads.items():
        if name in {"uk_gdp_revisions", "ct_crosswalk", "uk_gdp_forecast", "survey_context"}:
            require(all(row.get("scientific_source", row.get("source")) == research["source"] for row in rows),
                    "Browser extension exports mix scientific releases")
    return {"deployment": record["pages_source"], "research_source": research["source"],
            "downloads": len(downloads), "download_rows": sum(map(len, downloads.values())),
            "projected_rows": projections, "viewports": [320, 390, 1280]}
