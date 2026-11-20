"""Build point-in-time quarterly GDP from separately captured ONS release editions."""
from __future__ import annotations

import calendar
import math
import re
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from zipfile import ZipFile

from openpyxl import load_workbook

from .acquire import Source, acquire_one
from .io import ROOT, contained, digest, read_json, source_commit, write_json

RAW = ROOT / "data/chronology/raw"
DEFINITION = ROOT / "configs/uk-vintages-v7.json"
PINS = ROOT / "configs/uk-vintages-inputs.json"
RESULT = ROOT / "data/results/uk-vintages.json"
CATALOGUE = "/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi"
REFERENCE_QUARTER = re.compile(r"Q([1-4]) (19[0-9]{2}|20[0-9]{2})")
PUBLICATION_DAY = re.compile(r"Release date: </span><br/>\s*([0-9]{1,2} [A-Z][a-z]+ [0-9]{4})\s*<br")
EDITION_HEADER = re.compile(r"([A-Z][a-z]{2})-\s*((?:20)?[0-9]{2})\s*(?:\[[^\]]+\]\s*)?(1st|QNA)")


def pinned_items() -> list[dict]:
    pins = read_json(PINS)
    return [pins["catalogue"], *(row[field] for row in pins["editions"] for field in ("workbook", "bulletin"))]


def acquire_uk() -> dict:
    items = pinned_items()
    for pin in items:
        spec = Source(**{k: pin[k] for k in Source.__dataclass_fields__})
        receipt = acquire_one(spec, RAW)
        if receipt["sha256"] != pin["sha256"] or receipt["bytes"] != pin["bytes"]:
            raise ValueError(f"ONS archived release identity changed: {spec.id}")
    return {"sources": len(items)}


def checked(pin: dict) -> Path:
    path = contained(RAW, pin["path"])
    if path.stat().st_size != pin["bytes"] or digest(path) != pin["sha256"]:
        raise ValueError(f"ONS archived release identity changed: {pin['id']}")
    return path


def quarter_end(quarter: str) -> date:
    year = int(quarter[:4])
    month = int(quarter[-1]) * 3
    return date(year, month, calendar.monthrange(year, month)[1])


def original_day(bulletin: Path, pin: dict, row: dict, catalogue: str) -> str:
    html = bulletin.read_text(encoding="utf-8")
    dates = PUBLICATION_DAY.findall(html)
    title = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
    canonical = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    archive_path = row["workbook"]["url"].removeprefix("https://www.ons.gov.uk")
    if len(dates) != 1 or not title or unescape(title[1]) != row["bulletin_title"] or (
        not canonical or not pin["url"].endswith(canonical[1]) or CATALOGUE not in html
        or f'href="{archive_path}"' not in catalogue
    ):
        raise ValueError(f"ONS bulletin, catalogue and workbook do not identify one edition: {pin['id']}")
    day = datetime.strptime(dates[0], "%d %B %Y").date().isoformat()
    if day != row["release_day"] or bool('alert-bulletins--warning__title' in html) != row["has_notice"]:
        raise ValueError(f"ONS official release day or notice changed: {pin['id']}")
    return day


def archive_values(path: Path, row: dict, definition: dict) -> list[dict]:
    with ZipFile(path) as archive:
        inventory = archive.infolist()
        if not 0 < len(inventory) == len(set(archive.namelist())) <= 180 or (
            sum(member.file_size for member in inventory) > 25_000_000
        ):
            raise ValueError("ONS workbook exceeds the frozen archive bounds")
    with path.open("rb") as stream:
        workbook = load_workbook(stream, read_only=True, data_only=True)
        try:
            sheet = workbook[definition["sheet"]]
            if sheet.max_row > 350 or sheet.max_column > 120:
                raise ValueError("ONS workbook dimensions changed")
            records = enumerate(sheet.values, 1)
            headers = next(cells for i, cells in records if i == definition["header_row"])
            nonempty = [i for i, item in enumerate(headers) if item is not None]
            terminal = nonempty[-1]
            label = headers[terminal]
            matched = EDITION_HEADER.fullmatch(label)
            expected_day = date.fromisoformat(row["release_day"])
            if terminal + 1 != row["terminal_column"] or label != row["terminal_label"] or (
                not matched or (matched[1], matched[2][-2:], matched[3]) != (expected_day.strftime("%b"), expected_day.strftime("%y"),
                                                      "1st" if row["kind"] == "first" else "QNA")
            ):
                raise ValueError(f"ONS terminal release column differs from bulletin date or release type: {path.name}")
            observations = []
            previous = None
            for i, cells in records:
                reference = REFERENCE_QUARTER.fullmatch(str(cells[0]))
                if not reference:
                    continue
                quarter = f"{reference[2]}Q{reference[1]}"
                if quarter < definition["first_reference_quarter"]:
                    previous = cells[terminal]
                    continue
                level = cells[terminal]
                if quarter > row["quarter"]:
                    if level is not None:
                        raise ValueError("ONS archive contains a future quarter")
                    continue
                if type(level) not in {float, int} or not math.isfinite(level) or level <= 0:
                    raise ValueError("Unusable ONS archive cell inside the frozen period")
                if type(previous) not in {int, float} or previous <= 0:
                    raise ValueError("ONS preceding-quarter level is unavailable within the edition")
                observations.append({"quarter": quarter, "row": i, "level": level,
                                     "growth_pct": 100 * (level / previous - 1)})
                previous = level
            last_quarter = int(row["quarter"][:4]) * 4 + int(row["quarter"][-1])
            start = definition["first_reference_quarter"]
            expected = last_quarter - (int(start[:4]) * 4 + int(start[-1])) + 1
            if len(observations) != expected or observations[-1]["quarter"] != row["quarter"] or (
                len({item["quarter"] for item in observations}) != expected
            ):
                raise ValueError("ONS archive quarter support differs")
            return observations
        finally:
            workbook.close()


def as_of(editions: list[dict]) -> list[dict]:
    rows = []
    earlier = None
    for edition in editions:
        day = date.fromisoformat(edition["release_day"])
        for origin, snapshot in ((day - timedelta(days=1), earlier), (day, edition)):
            latest = snapshot["observations"][-1] if snapshot else None
            rows.append({
                "origin": origin.isoformat(), "anchor": edition["release_id"],
                "available_release": snapshot["release_id"] if snapshot else None,
                "available_day": snapshot["release_day"] if snapshot else None,
                "available_quarter": latest["quarter"] if latest else None,
                "available_growth_pct": latest["growth_pct"] if latest else None,
                "days_since_available_release": (origin - date.fromisoformat(snapshot["release_day"])).days if snapshot else None,
            })
        earlier = edition
    return rows


def revisions(editions: list[dict], definition: dict) -> list[dict]:
    releases = {(row["quarter"], row["kind"]): row for row in editions}
    rows = []
    for quarter in definition["expected_quarters"]:
        first, revised = (releases.get((quarter, kind)) for kind in ("first", "qna"))
        v1 = first["observations"][-1]["growth_pct"] if first else None
        v2 = revised["observations"][-1]["growth_pct"] if revised else None
        change = (v2 - v1) if v1 is not None and v2 is not None else None
        rows.append({"quarter": quarter, "first_release": first["release_day"] if first else None,
                     "qna_release": revised["release_day"] if revised else None, "first_growth_pct": v1,
                     "qna_growth_pct": v2, "revision_pp": change,
                     "substantive_revision": abs(change) >= definition["threshold_pp"] if change is not None else None,
                     "strict_sign_change": v1 * v2 < 0 if change is not None else None})
    return rows


def build_uk() -> dict:
    definition, pins = read_json(DEFINITION), read_json(PINS)
    catalog = checked(pins["catalogue"]).read_text(encoding="utf-8")
    editions = []
    for row in pins["editions"]:
        book, bulletin = row["workbook"], row["bulletin"]
        day = original_day(checked(bulletin), bulletin, row, catalog)
        if date.fromisoformat(day) <= quarter_end(row["quarter"]):
            raise ValueError("ONS release precedes the reference-quarter end")
        editions.append({
            "release_id": book["id"], "quarter": row["quarter"], "kind": row["kind"], "release_day": day,
            "workbook_sha256": book["sha256"], "workbook_url": book["url"], "capture_at": book["acquired_at"],
            "bulletin_sha256": bulletin["sha256"], "bulletin_url": bulletin["url"], "has_notice": row["has_notice"],
            "terminal_column": row["terminal_column"], "terminal_label": row["terminal_label"],
            "observations": archive_values(checked(book), row, definition),
        })
    editions.sort(key=lambda row: row["release_day"])
    if len({row["release_day"] for row in editions}) != len(editions) or (
        len({(row["quarter"], row["kind"]) for row in editions}) != len(editions)
    ):
        raise ValueError("ONS overlapping or repeated release dates")
    result = {"schema_version": 1, "source": source_commit(), "definition_sha256": digest(DEFINITION),
              "inputs_sha256": digest(PINS), "series": definition["series"], "unit": definition["unit"],
              "availability_scope": definition["availability_scope"], "editions": editions,
              "unavailable": pins["unavailable"], "revisions": revisions(editions, definition),
              "as_of": as_of(editions)}
    write_json(RESULT, result)
    return result
