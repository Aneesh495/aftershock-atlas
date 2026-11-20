"""Reconstruct registered education and hours estimates from frozen sources."""

from __future__ import annotations

import math
import os
from pathlib import Path
from statistics import median
from zipfile import ZipFile

from openpyxl import load_workbook
from openpyxl.utils.cell import get_column_letter

from .acquire import Source, acquire_one
from .io import ROOT, contained, digest, exclusive, read_json, source_commit, write_json
from .resources import usage
from .statistics import bh_adjust

CONFIG = ROOT / "configs/measurement-v4.json"
RAW = ROOT / "data/measurement/raw"
RESULT = ROOT / "data/results/measurement-v4.json"
ARCHIVE_LIMIT = 25_000_000
PISA_KIND = "OECD weighted mean for the assessment-eligible enrolled population"
PISA_UNIT = "PISA scale points"
Z95 = 1.959963984540054


def input_manifest() -> dict:
    config = read_json(CONFIG)
    manifest = dict(config["sources"])
    hours = ROOT / "configs/measurement-hours.json"
    if hours.exists():
        manifest.update(read_json(hours))
    return manifest


def acquire_measurement() -> dict:
    """Retrieve each official source and check it against its registered bytes."""
    sources = input_manifest()
    snapshots = read_json(ROOT / "configs/MEASUREMENT_SNAPSHOT.json")
    with exclusive(RAW / ".acquire.lock"):
        for identity, record in sources.items():
            local = contained(RAW, record["path"])
            if local.exists():
                pinned_file(RAW, record)
                continue
            spec = {k: record[k] for k in Source.__dataclass_fields__}
            if identity in snapshots:
                if not record["redistribute"]:
                    raise ValueError("Protected measurement inputs cannot use public mirrors")
                spec.update(id=identity + "_snapshot", url=snapshots[identity]["url"])
            received = acquire_one(Source(**spec), RAW)
            if (received["sha256"], received["bytes"]) != (record["sha256"], record["bytes"]):
                raise ValueError(f"Measurement source {identity} drifted from its registered vintage")
            restored = contained(RAW, received["path"])
            if restored != local:
                local.parent.mkdir(parents=True, exist_ok=True)
                os.link(restored, local)
        write_json(RAW / "index.json", sources)
    return {key: "acquired" for key in sources}


def pinned_file(root: Path, record: dict) -> Path:
    path = root / record["path"]
    if path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
        raise ValueError(f"Measurement source identity mismatch: {record['id']}")
    return path


def workbook_bounds(path: Path) -> None:
    with ZipFile(path) as archive:
        members = archive.infolist()
        names = {member.filename for member in members}
        if len(members) > 180 or len(members) != len(names):
            raise ValueError("Unexpected workbook file inventory")
        if sum(member.file_size for member in members) > ARCHIVE_LIMIT:
            raise ValueError("Expanded learning workbook exceeds its bound")
        if any(name.startswith("/") or ".." in Path(name).parts for name in names):
            raise ValueError("Invalid workbook member")


def score(cell: object) -> tuple[float | None, str | None]:
    if type(cell) in {float, int} and math.isfinite(cell):
        return float(cell), None
    if cell is None:
        return None, "blank"
    if isinstance(cell, str) and (
        cell in {"a", "c", "m", "w", "x"} or cell.startswith("x(") and cell.endswith(")")
    ):
        return None, cell
    raise ValueError("Unknown or nonfinite assessment score cell")


def interval(value: float | None, standard_error: float | None) -> tuple[float | None, float | None]:
    if value is None or standard_error is None:
        return None, None
    if standard_error <= 0:
        raise ValueError("Published assessment standard error must be positive")
    return value - Z95 * standard_error, value + Z95 * standard_error


def assessment_rows(path: Path, config: dict, source_hash: str) -> list[dict]:
    workbook_bounds(path)
    workbook = load_workbook(path, read_only=True, data_only=True)
    rows = []
    try:
        for subject, layout in config["sheets"].items():
            sheet = workbook[layout["name"]]
            if sheet.max_row > 150 or sheet.max_column > 80:
                raise ValueError("Unexpected assessment table dimensions")
            header = next(sheet.iter_rows(min_row=8, max_row=8, values_only=True))
            if [header[c - 1] for c in layout["means"]] != [f"PISA {y}" for y in config["cycle_years"]]:
                raise ValueError("Assessment source cycles shifted")
            if header[layout["change"] - 1].splitlines()[0].strip() != "PISA 2018":
                raise ValueError("Assessment change-column baseline shifted")
            observed = set()
            subject_rows = []
            for start, stop in config["system_row_ranges"]:
                cells = sheet.iter_rows(min_row=start, max_row=stop, values_only=True)
                for row_number, cells_row in enumerate(cells, start):
                    label = cells_row[0]
                    system = label.rstrip("*").strip()
                    if system in observed or system not in config["systems"]:
                        raise ValueError("Unexpected or repeated assessment system")
                    observed.add(system)
                    subject_rows.append(
                        learning_record(subject, system, label, row_number, cells_row, layout, config, source_hash)
                    )
            if observed != set(config["systems"]):
                raise ValueError("Assessment system inventory mismatch")
            eligible = [r for r in subject_rows if not r["caution"] and r["p_value"] is not None]
            for row, q in zip(eligible, bh_adjust([r["p_value"] for r in eligible]), strict=True):
                row["q_value"] = q
            rows.extend(subject_rows)
    finally:
        workbook.close()
    return rows


def learning_record(
    subject: str, system: str, label: str, number: int, cells: tuple, layout: dict, config: dict, source_hash: str
) -> dict:
    def read(column: int) -> dict:
        value, missing = score(cells[column - 1])
        se, se_missing = score(cells[column])
        low, high = interval(value, se)
        return {
            "value": value, "missing": missing, "se": se, "se_missing": se_missing,
            "lower": low, "upper": high, "source_cell": f"{get_column_letter(column)}{number}",
            "se_cell": f"{get_column_letter(column + 1)}{number}",
        }

    cycles = {str(y): read(c) for y, c in zip(config["cycle_years"], layout["means"], strict=True)}
    published = read(layout["change"])
    m15, m18, m22 = (cycles[str(y)]["value"] for y in config["cycle_years"])
    early = m18 - m15 if m15 is not None and m18 is not None else None
    reconstructed = m22 - m18 if m22 is not None and m18 is not None else None
    delta = published["value"]
    if delta is not None and (
        reconstructed is None
        or abs(delta - reconstructed) > config["mean_reconciliation_tolerance"]
    ):
        raise ValueError("Published assessment change contradicts released means")
    caution = "linkage" if label.endswith("**") else "sampling" if label.endswith("*") else None
    p_value = None
    if delta is not None and published["se"] is not None:
        p_value = math.erfc(abs(delta / published["se"]) / math.sqrt(2))
    return {
        "subject": subject, "system": system, "source_label": label, "caution": caution,
        "atlas_region": config["systems"][system], "unit": PISA_UNIT, "population": PISA_KIND,
        "source_sha256": source_hash, "sheet": layout["name"], "row": number, "cycles": cycles,
        "2015_to_2018": early, "2018_to_2022_reconstructed": reconstructed,
        "2018_to_2022_released": published, "p_value": p_value, "q_value": None,
    }


def learning_summary(rows: list[dict]) -> list[dict]:
    summary = []
    for subject in sorted({r["subject"] for r in rows}):
        systems = [r for r in rows if r["subject"] == subject]
        for include_caution in (False, True):
            matched = [
                r for r in systems
                if (include_caution or not r["caution"])
                and r["2018_to_2022_released"]["value"] is not None
            ]
            values = [r["2018_to_2022_released"]["value"] for r in matched]
            summary.append({
                "subject": subject, "includes_caution": include_caution,
                "systems_in_workbook": len(systems), "matched_systems": len(matched),
                "below_2018": sum(x < 0 for x in values), "above_2018": sum(x > 0 for x in values),
                "no_change": sum(x == 0 for x in values),
                "median_change_points": median(values) if values else None,
                "adjusted_declines": sum(
                    r["q_value"] is not None and r["q_value"] <= .05
                    and r["2018_to_2022_released"]["value"] < 0 for r in matched
                ) if not include_caution else None,
                "adjusted_increases": sum(
                    r["q_value"] is not None and r["q_value"] <= .05
                    and r["2018_to_2022_released"]["value"] > 0 for r in matched
                ) if not include_caution else None,
            })
    return summary


def run_measurement() -> dict:
    from .remote_instruction import instruction_estimates
    from .work_hours import hours_study

    usage(300_000_000)
    config = read_json(CONFIG)
    sources = input_manifest()
    pisa = sources["pisa_2022_b15"]
    rows = assessment_rows(pinned_file(RAW, pisa), config["pisa"], pisa["sha256"])
    survey = read_json(ROOT / "configs/survey-inputs.json")["hps_week1"]
    remote = instruction_estimates(
        pinned_file(ROOT / "data/private-survey", survey), config["census"], survey["sha256"]
    )
    result = {
        "protocol": config["version"], "source": source_commit(), "definition_sha256": digest(CONFIG),
        "sources": sources,
        "learning": {"rows": rows, "summary": learning_summary(rows),
                     "change_se_basis": config["pisa"]["change_se_basis"]},
        "remote_instruction": remote, "hours": hours_study(sources, config["hours"]),
    }
    write_json(RESULT, result)
    return {
        "learning_system_subject_rows": len(rows), "instruction_aggregates": len(remote["rows"]),
        "hours_status": result["hours"]["status"], "artifact_sha256": digest(RESULT),
    }
