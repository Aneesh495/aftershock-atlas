"""Reconcile Connecticut's statistical county change at a conserved resident denominator."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

from .acquire import Source, acquire_one
from .io import ROOT, digest, read_json, source_commit, write_json

CONFIG = ROOT / "configs/ct-crosswalk-v7.json"
PINS = ROOT / "configs/ct-crosswalk-inputs.json"
RAW = ROOT / "data/chronology/raw"
RESULT = ROOT / "data/results/ct-crosswalk.json"


def acquire_ct() -> dict:
    sources = read_json(PINS)
    for key, pin in sources.items():
        spec = Source(**{k: pin[k] for k in Source.__dataclass_fields__})
        received = acquire_one(spec, RAW)
        if (received["bytes"], received["sha256"]) != (pin["bytes"], pin["sha256"]):
            raise ValueError(f"Connecticut source changed: {key}")
    return {"sources": len(sources)}


def crosswalk(path: Path, config: dict) -> tuple[dict, dict, int]:
    column_names = (
        "STATEFP (INCITS38)", "OLD_COUNTYFP (INCITS31)", "OLD_COUNTY_NAMELSAD",
        "NEW_COUNTYFP (INCITS31)", "NEW_COUNTY_NAMELSAD", "COUSUBFP", "OLD_COUSUB_GEOID",
        "NEW_COUSUB_GEOID", "COUSUB_NAMELSAD", "COUSUBNS (INCITS446)", "COUSUB_LSAD",
        "COUSUB_FUNCSTAT", "COUSUB_CLASSFP",
    )
    towns = {}
    water: dict[str, set[str]] = defaultdict(set)
    water_links = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        table = csv.reader(stream, delimiter="|")
        if tuple(" ".join(cell.split()) for cell in next(table)) != column_names:
            raise ValueError("Unexpected Connecticut relationship file columns")
        for cells in table:
            if cells == ["GLOSSARY"]:
                break
            if not cells:
                continue
            state, o, old_name, n, new_name, town, previous, current, name, ns, lsad, status, group = cells
            old, new = state + o, state + n
            if state != config["state"] or previous != old + town or current != new + town:
                raise ValueError("Crosswalk county-subdivision identifier mismatch")
            if group == "Z9" and status == "F":
                if current in water[previous]:
                    raise ValueError("Repeated geographic water relationship")
                water[previous].add(current)
                water_links += 1
                continue
            if (group, status) not in {("T1", "A"), ("T5", "C")} or lsad != "43" or previous in towns:
                raise ValueError("Unknown or duplicate municipal split relationship")
            towns[previous] = {"old_municipality": previous, "new_municipality": current,
                               "old_county": old, "old_county_name": old_name,
                               "planning_region": new, "planning_region_name": new_name,
                               "municipality": name, "municipality_ns": ns}
    if len(towns) != config["municipalities"] or len(water) != config["water_geographies"] or (
        water_links != config["water_relationships"] or len(towns) + water_links != config["relationship_rows"]
    ):
        raise ValueError("Crosswalk inventory differs from the frozen release")
    return towns, dict(water), water_links


def census(path: Path, config: dict) -> dict:
    columns = config["geo_indices"]
    records = {}
    source_levels = set(config["levels"].values())
    with ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != 4 or set(archive.namelist()) != set(config["archive_members"]) or (
            sum(member.file_size for member in members) > 160_000_000
        ):
            raise ValueError("Connecticut PL94 archive member or expansion bound")
        with archive.open("ctgeo2020.pl") as binary:
            table = csv.reader(io.TextIOWrapper(binary, encoding="utf-8", newline=""), delimiter="|")
            for cells in table:
                if cells[columns["summary"]] not in source_levels:
                    continue
                if len(cells) != 97 or cells[columns["state"]] != config["state"]:
                    raise ValueError("Connecticut geographic record shape or state differs")
                county, identifier, level, logical, name, population = (
                    cells[columns[k]] for k in ("county", "geoid", "summary", "logical_record", "name", "population")
                )
                if logical in records or int(population) < 0:
                    raise ValueError("Duplicate geographic record or invalid resident count")
                records[logical] = {"geoid": identifier, "county": county, "level": level,
                                    "name": name, "residents": int(population), "logical_record": logical}
        if len(records) != 1 + 8 + config["municipalities"] + config["water_geographies"]:
            raise ValueError("Connecticut Census summary population changed")
        with archive.open("ct000012020.pl") as binary:
            table = csv.reader(io.TextIOWrapper(binary, encoding="utf-8", newline=""), delimiter="|")
            matched = set()
            for cells in table:
                if (identifier := cells[config["p1_indices"]["logical_record"]]) not in records:
                    continue
                if identifier in matched or len(cells) != 149 or int(cells[config["p1_indices"]["population"]]) != records[identifier]["residents"]:
                    raise ValueError("Census GEO and P1 resident populations disagree")
                matched.add(identifier)
    if matched != records.keys():
        raise ValueError("Census geography without a P1 population row")
    return {row["geoid"]: row for row in records.values()}


def matrix(towns: dict, zero_residents: dict, population: dict, config: dict) -> dict:
    for old in zero_residents:
        if population[old]["residents"] != 0:
            raise ValueError("Water relationship has nonzero resident population")
    old_counts = {key: data["residents"] for key, data in population.items() if data["level"] == "050"}
    geo_towns = {key for key, data in population.items() if data["level"] == "060"}
    if set(towns) | set(zero_residents) != geo_towns or set(towns) & set(zero_residents):
        raise ValueError("Connecticut municipal Census and crosswalk population mismatch")
    bonds = defaultdict(lambda: {"residents": 0, "municipalities": 0})
    named_destinations = {}
    for key, town in sorted(towns.items()):
        census_row = population[key]
        old, new = town["old_county"], town["planning_region"]
        if census_row["name"] + " town" != town["municipality"] or config["state"] + census_row["county"] != old:
            raise ValueError("Census town labels and relationship file disagree")
        record = bonds[old, new]
        record["residents"] += census_row["residents"]
        record["municipalities"] += 1
        named_destinations[new] = town["planning_region_name"]
        town.update(residents=census_row["residents"], source_record=census_row["logical_record"])
    old_sums, new_sums = defaultdict(int), defaultdict(int)
    for (old, new), record in bonds.items():
        old_sums[old] += record["residents"]
        new_sums[new] += record["residents"]
    reference = population[config["state"]]["residents"]
    if dict(old_sums) != old_counts or dict(new_sums) != config["planning_benchmarks"] or (
        sum(old_sums.values()) != reference or reference != config["state_benchmark"]
    ):
        raise ValueError("Resident mass does not reconcile to independent county, region and state totals")
    by_origin = defaultdict(list)
    overlaps = []
    for (old, new), record in sorted(bonds.items()):
        by_origin[old].append(new)
        overlaps.append({"old_county": old, "planning_region": new, **record,
                         "old_county_residents": old_counts[old], "planning_region_residents": new_sums[new],
                         "share_of_old_county": record["residents"] / old_counts[old],
                         "share_of_planning_region": record["residents"] / new_sums[new]})
    return {"resident_population": reference, "overlaps": overlaps,
            "old_counties": [
                {"geoid": old, "name": population[old]["name"] + " County", "residents": count,
                 "planning_regions": by_origin[old], "county_only_counts_ambiguous": len(by_origin[old]) > 1}
                for old, count in sorted(old_counts.items())
            ],
            "planning_regions": [
                {"geoid": new, "name": named_destinations[new], "residents": total}
                for new, total in sorted(new_sums.items())
            ],
            "municipalities": [town for _, town in sorted(towns.items())],
            "zero_population_geographies": [
                {"old_geoid": old, "new_geoids": sorted(destinations), "residents": 0}
                for old, destinations in sorted(zero_residents.items())
            ]}


def build_ct() -> dict:
    config, pins = read_json(CONFIG), read_json(PINS)
    local = {}
    for key, record in pins.items():
        path = RAW / record["path"]
        if not path.is_file() or path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
            raise ValueError(f"Connecticut frozen data identity changed: {key}")
        local[key] = path
    towns, water, links = crosswalk(local["ct_crosswalk"], config)
    counts = census(local["ct_2020_census"], config)
    measures = matrix(towns, water, counts, config)
    data = {
        "schema_version": 1, "source": source_commit(), "definition_sha256": digest(CONFIG),
        "inputs_sha256": digest(PINS), "water_relationships": links,
        "notice_date": config["notice_date"], "tiger_boundary_date": config["tiger_boundary_date"],
        "tiger_release_date": config["tiger_release_date"], "acs_vintage": config["acs_vintage"],
        "population_day": config["population_day"], "population_basis": config["population_basis"],
        "limitations": config["limitation"], **measures,
    }
    write_json(RESULT, data)
    return data
