"""Independently replay ONS workbook cells and origin cutoffs from primary files."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from zipfile import ZipFile

from .io import ROOT, contained, digest, read_json
from .verification import require
from .verify_measurement import same, spreadsheet_cells


class Publication(HTMLParser):
    def __init__(self, source: str):
        super().__init__()
        self.links = set()
        self.tokens = []
        self.notice = False
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag in {"a", "link"} and "href" in fields:
            self.links.add(fields["href"])
        self.notice |= "alert-bulletins--warning__title" in fields.get("class", "").split()

    def handle_data(self, text):
        if item := text.strip():
            self.tokens.append(item)


def restore(pin: dict):
    path = contained(ROOT / "data/chronology/raw", pin["path"])
    require(path.stat().st_size == pin["bytes"] and digest(path) == pin["sha256"], "ONS raw release or catalogue differs")
    return path


def column_ref(index: int) -> str:
    text = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        text = chr(65 + remainder) + text
    return text


def within_edition(book: dict, observed: dict, config: dict, pin: dict) -> float:
    col = column_ref(pin["terminal_column"])
    header_row = config["header_row"]
    require(book[f"{col}{header_row}"] == pin["terminal_label"] and not any(
        value is not None and (match := re.fullmatch(r"([A-Z]+)([0-9]+)", cell))
        and int(match[2]) == header_row and (len(match[1]), match[1]) > (len(col), col)
        for cell, value in book.items()
    ), "ONS terminal workbook column changed")
    rows = []
    previous = None
    for index in range(header_row + 1, 351):
        label = str(book.get(f"A{index}", "")).split()
        if len(label) != 2 or not re.fullmatch(r"Q[1-4]", label[0]) or not label[1].isdigit():
            continue
        quarter = label[1] + label[0]
        level = book.get(f"{col}{index}")
        if quarter < config["first_reference_quarter"]:
            previous = level
            continue
        if quarter > pin["quarter"]:
            require(level is None, "Future ONS quarter in raw vintage")
            continue
        require(isinstance(level, float) and isinstance(previous, float) and min(level, previous) > 0,
                "ONS quarter has no positive within-vintage levels")
        rows.append((quarter, index, level, 100 * (level - previous) / previous))
        previous = level
    expected_first = int(config["first_reference_quarter"][:4]) * 4 + int(config["first_reference_quarter"][-1])
    ordinals = [int(q[:4]) * 4 + int(q[-1]) for q, _, _, _ in rows]
    require(rows[-1][0] == pin["quarter"] and ordinals == list(range(expected_first, expected_first + len(rows)))
            and len(rows) == len(observed["observations"]), "ONS quarterly record population differs")
    for occurrence, (quarter, index, level, growth) in zip(observed["observations"], rows, strict=True):
        require(occurrence["quarter"] == quarter and occurrence["row"] == index, "ONS source row or quarter differs")
        same(occurrence["level"], level, "ONS GDP level differs from archived workbook cell")
        same(occurrence["growth_pct"], growth, "ONS GDP growth does not use comparable within-edition cells")
    return rows[-1][-1]


def verify_uk(data: dict, source: str) -> dict:
    definition = ROOT / "configs/uk-vintages-v7.json"
    pins = ROOT / "configs/uk-vintages-inputs.json"
    config, manifest = read_json(definition), read_json(pins)
    require(data["schema_version"] == 1 and data["source"] == source
            and data["definition_sha256"] == digest(definition) and data["inputs_sha256"] == digest(pins)
            and data["unit"] == config["unit"] and data["series"] == config["series"]
            and data["availability_scope"] == config["availability_scope"], "ONS provenance, availability scope or unit changed")
    require(data["unavailable"] == manifest["unavailable"] and len(data["editions"]) == len(manifest["editions"]),
            "ONS missing release evidence was changed")
    require({(row["quarter"], row["kind"]) for row in (*manifest["editions"], *manifest["unavailable"])}
            == {(quarter, kind) for quarter in config["expected_quarters"] for kind in ("first", "qna")},
            "ONS expected quarterly release inventory differs")
    catalogue = Publication(restore(manifest["catalogue"]).read_text(encoding="utf-8"))
    by_day, by_quarter = {}, {}
    cells = 0
    for row, recorded in zip(sorted(manifest["editions"], key=lambda r: r["release_day"]), data["editions"], strict=True):
        book, bulletin = row["workbook"], row["bulletin"]
        published = Publication(restore(bulletin).read_text(encoding="utf-8"))
        idx = published.tokens.index("Release date:")
        day = datetime.strptime(published.tokens[idx + 1], "%d %B %Y").date()
        expected_day = date.fromisoformat(row["release_day"])
        require(day == expected_day and day not in by_day
                and published.notice == row["has_notice"] and row["bulletin_title"] in published.tokens,
                "ONS original release date, heading or notice differs")
        release_month, release_yy, release_kind = re.match(
            r"^([A-Z][a-z]{2})-\s*((?:20)?[0-9]{2})\s+(?:\[[^\]]+\]\s+)?(1st|QNA)$",
            row["terminal_label"],
        ).groups()
        require(datetime.strptime(f"{release_month} {release_yy[-2:]}", "%b %y").date().replace(day=1) == day.replace(day=1)
                and release_kind == ("1st" if row["kind"] == "first" else "QNA")
                and (day.year, (day.month - 1) // 3 + 1) > (int(row["quarter"][:4]), int(row["quarter"][-1]))
                and book["url"].removeprefix("https://www.ons.gov.uk") in catalogue.links
                and "https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi" in published.links,
                "ONS workbook label, catalogue or historical calendar mismatch")
        expected_release = {k: row[k] for k in ("quarter", "kind", "release_day", "terminal_column", "terminal_label", "has_notice")}
        expected_release.update(release_id=book["id"], workbook_sha256=book["sha256"], workbook_url=book["url"],
                                capture_at=book["acquired_at"], bulletin_sha256=bulletin["sha256"], bulletin_url=bulletin["url"])
        require({k: recorded[k] for k in expected_release} == expected_release, "ONS release evidence detached from raw editions")
        with ZipFile(restore(book)) as contents:
            workbook = spreadsheet_cells(contents, {config["sheet"]})[config["sheet"]]
        growth = within_edition(workbook, recorded, config, row)
        cells += len(recorded["observations"])
        index = (row["quarter"], row["kind"])
        require(index not in by_quarter, "Duplicate ONS release quarter and kind")
        by_quarter[index] = (day.isoformat(), growth)
        by_day[day] = (book["id"], row["quarter"], growth)

    require(len(data["as_of"]) == 2 * len(by_day), "ONS missing pre-release or release-date comparison")
    for index, row in enumerate(data["as_of"]):
        anchor = sorted(by_day)[index // 2]
        origin = anchor - timedelta(days=1 - index % 2)
        latest = max((candidate for candidate in by_day if candidate <= origin), default=None)
        release_id, quarter, growth = by_day[latest] if latest else (None, None, None)
        require(row["origin"] == origin.isoformat() and row["anchor"] == by_day[anchor][0]
                and row["available_release"] == release_id and row["available_quarter"] == quarter
                and row["available_day"] == (latest.isoformat() if latest else None)
                and row["days_since_available_release"] == ((origin - latest).days if latest else None),
                "ONS as-of replay selects a future or incomplete release")
        same(row["available_growth_pct"], growth, "ONS as-of growth detached from latest released archive")

    require([row["quarter"] for row in data["revisions"]] == config["expected_quarters"], "ONS missing revision population")
    matches = 0
    for row in data["revisions"]:
        first_day, first = by_quarter.get((row["quarter"], "first"), (None, None))
        revision_day, revised = by_quarter.get((row["quarter"], "qna"), (None, None))
        change = revised - first if first is not None and revised is not None else None
        require(row["first_release"] == first_day and row["qna_release"] == revision_day
                and (change is None or first_day < revision_day), "ONS original and revision chronology differs")
        same(row["first_growth_pct"], first, "ONS first estimate growth altered")
        same(row["qna_growth_pct"], revised, "ONS revised growth altered")
        same(row["revision_pp"], change, "ONS magnitude of quarterly revision altered")
        require(row["substantive_revision"] == (abs(change) >= config["threshold_pp"] if change is not None else None)
                and row["strict_sign_change"] == (first * revised < 0 if change is not None else None),
                "ONS quarterly revision classifications altered")
        matches += change is not None
    return {"editions": len(by_day), "workbook_cells": cells, "paired_quarters": matches,
            "origin_checks": len(data["as_of"]), "unavailable_editions": len(data["unavailable"])}
