"""Replay Connecticut's resident geography from archived text records."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from .io import ROOT, contained, digest, read_json
from .verification import require
from .verify_measurement import same

def verify_ct(data: dict, source: str, raw: Path | None = None) -> dict:
    raw = raw or ROOT / "data/chronology/raw"
    definitions = ROOT / "configs/ct-crosswalk-v7.json"
    pins = ROOT / "configs/ct-crosswalk-inputs.json"
    cfg = read_json(definitions)
    require(data["schema_version"] == 1 and data["source"] == source
            and data["definition_sha256"] == digest(definitions) and data["inputs_sha256"] == digest(pins),
            "Connecticut provenance differs")
    for field in ("notice_date", "tiger_boundary_date", "tiger_release_date", "acs_vintage",
                  "population_day", "population_basis"):
        require(data[field] == cfg[field], "Connecticut reference geography or dates differ")
    require(data["limitations"] == cfg["limitation"], "Connecticut resident weights promoted to event counts")

    paths = {}
    for key, record in read_json(pins).items():
        path = contained(raw, record["path"])
        require(path.stat().st_size == record["bytes"] and digest(path) == record["sha256"],
                "Connecticut raw reference mismatch")
        paths[key] = path

    with ZipFile(paths["ct_2020_census"]) as archive:
        members = archive.infolist()
        require(len(members) == 4 and sum(entry.file_size for entry in members) <= 160_000_000,
                "Connecticut Census expansion bound")
        with archive.open("ctgeo2020.pl") as census:
            records = {}
            for line in census:
                cols = line.decode("utf-8").rstrip("\r\n").split("|")
                if cols[2] in ("040", "050", "060"):
                    records[cols[9]] = (cols[2], cols[7], cols[14], cols[86], int(cols[90]))
        selected = {logical for _, logical, _, _, _ in records.values()}
        with archive.open("ct000012020.pl") as segment:
            p1 = {}
            for line in segment:
                fields = line.split(b"|", 6)
                logical = fields[4].decode("ascii")
                if logical in selected:
                    require(logical not in p1, "Connecticut repeated P1 geographic row")
                    p1[logical] = int(fields[5])
    require(len(records) == len(selected) and len(p1) == len(selected), "Connecticut Census inventory does not reconcile")
    require(all(row[-1] == p1[row[1]] for row in records.values()), "Connecticut geographic and P1 counts differ")

    towns, water = {}, {}
    old_totals = {geo: row[-1] for geo, row in records.items() if row[0] == "050"}
    old_names = {geo: row[3] + " County" for geo, row in records.items() if row[0] == "050"}
    new_names = {}
    overlaps: Counter = Counter()
    overlap_towns: Counter = Counter()
    relationship_lines = paths["ct_crosswalk"].read_text(encoding="utf-8-sig").splitlines()
    crosswalk = [line for line in relationship_lines if line.startswith("09|")]
    for relation in crosswalk:
        state, oc, old_label, nr, new_label, subdivision, old, new, name, ns, legal, status, category = (
            relation.split("|")
        )
        require(old == state + oc + subdivision and new == state + nr + subdivision,
                "Connecticut ambiguous municipal relationship")
        level, logical, county, label, population = records[old]
        if category == "Z9":
            require(level == "060" and population == 0 and status == "F", "Connecticut water geography contains residents")
            water.setdefault(old, []).append(new)
            continue
        require(level == "060" and county == oc and legal == "43" and name == label + " town"
                and (status, category) in {("A", "T1"), ("C", "T5")}
                and old not in towns and old_label == old_names[state + oc], "Connecticut municipality does not match Census")
        old_county, region = state + oc, state + nr
        new_names[region] = new_label
        towns[old] = {
            "old_municipality": old, "new_municipality": new, "old_county": old_county,
            "old_county_name": old_label, "planning_region": region, "planning_region_name": new_label,
            "municipality": name, "municipality_ns": ns, "residents": population, "source_record": logical,
        }
        overlaps[old_county, region] += population
        overlap_towns[old_county, region] += 1

    require(set(towns).isdisjoint(water) and set(towns) | set(water) == {k for k, v in records.items() if v[0] == "060"},
            "Connecticut missing or duplicated geography")
    require(len(crosswalk) == cfg["relationship_rows"] and len(towns) == cfg["municipalities"]
            and len(water) == cfg["water_geographies"], "Connecticut crosswalk inventory differs")
    require(data["water_relationships"] == cfg["water_relationships"] == sum(map(len, water.values()))
            and data["zero_population_geographies"] == [
                {"old_geoid": old, "new_geoids": sorted(destinations), "residents": 0}
                for old, destinations in sorted(water.items())
            ], "Connecticut zero-population relationships altered")
    require(data["municipalities"] == [row for _, row in sorted(towns.items())]
            and len({row["new_municipality"] for row in towns.values()}) == len(towns),
            "Connecticut municipal allocation differs from original crosswalk")

    new_totals = {region: sum(v for (_, target), v in overlaps.items() if target == region) for region in new_names}
    require(new_totals == cfg["planning_benchmarks"]
            and sum(new_totals.values()) == data["resident_population"] == records["09"][-1] == cfg["state_benchmark"],
            "Connecticut state and planning region resident totals do not conserve")
    require(data["planning_regions"] == [
        {"geoid": geo, "name": new_names[geo], "residents": count} for geo, count in sorted(new_totals.items())
    ], "Connecticut planning region population differs")
    expected_counties = []
    for county, total in sorted(old_totals.items()):
        regions = sorted(target for origin, target in overlaps if origin == county)
        require(sum(overlaps[county, target] for target in regions) == total, "Connecticut historic county total differs")
        expected_counties.append({
            "geoid": county, "name": old_names[county], "residents": total, "planning_regions": regions,
            "county_only_counts_ambiguous": len(regions) != 1,
        })
    require(data["old_counties"] == expected_counties, "Connecticut historic assignment ambiguity differs")

    require(len(data["overlaps"]) == len(overlaps), "Connecticut overlap inventory differs")
    for key, row in zip(sorted(overlaps), data["overlaps"], strict=True):
        old, new = key
        count = overlaps[key]
        require((row["old_county"], row["planning_region"]) == key
                and row["residents"] == count and row["municipalities"] == overlap_towns[key]
                and row["old_county_residents"] == old_totals[old] and row["planning_region_residents"] == new_totals[new],
                "Connecticut overlap population allocation differs")
        same(row["share_of_old_county"], count / old_totals[old], "Connecticut historic resident share differs")
        same(row["share_of_planning_region"], count / new_totals[new], "Connecticut planning region resident share differs")
    return {"municipalities": len(towns), "county_region_links": len(overlaps), "residents": data["resident_population"],
            "ambiguous_counties": sum(row["county_only_counts_ambiguous"] for row in expected_counties)}
