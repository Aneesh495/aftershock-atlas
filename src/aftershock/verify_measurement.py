"""Read original XML, CSV and survey weights independently of the study pipeline."""

from __future__ import annotations

import csv
import io
import math
import posixpath
from pathlib import Path
from statistics import median
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import numpy as np

from .io import ROOT, contained, digest, read_json
from .verification import require

X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELATIONSHIP = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
SE_CRITICAL = 1.959963984540054


def same(actual: float | None, expected: float | None, reason: str) -> None:
    if expected is None:
        require(actual is None, reason)
    else:
        require(
            type(actual) in {int, float} and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-9),
            reason,
        )


def spreadsheet_cells(archive: ZipFile, sheet_names: set[str]) -> dict:
    raw = archive.infolist()
    require(len(raw) == len(set(archive.namelist())) <= 180, "Assessment workbook member count")
    require(sum(m.file_size for m in raw) <= 25_000_000, "Assessment workbook expanded size")
    relations = {
        c.attrib["Id"]: c.attrib["Target"] for c in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    }
    strings = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings = ["".join(x.text or "" for x in item.iter(X + "t")) for item in root]
    output = {}
    for sheet in ET.fromstring(archive.read("xl/workbook.xml")).iter(X + "sheet"):
        name = sheet.attrib["name"]
        if name not in sheet_names:
            continue
        target = relations[sheet.attrib[RELATIONSHIP]]
        path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        require(path.startswith("xl/worksheets/"), "Assessment workbook worksheet path")
        cells = {}
        for item in ET.fromstring(archive.read(path)).iter(X + "c"):
            ref = item.attrib["r"]
            value = item.findtext(X + "v")
            kind = item.get("t", "n")
            if kind == "inlineStr":
                cells[ref] = "".join(x.text or "" for x in item.iter(X + "t"))
            elif value is not None:
                cells[ref] = strings[int(value)] if kind == "s" else float(value) if kind == "n" else value
        output[name] = cells
    return output


def verify_learning(path: Path, data: dict, config: dict, sha: str) -> int:
    layouts = {
        "mathematics": ("Table I.B1.5.4", ("J", "K", "L", "M", "N", "O", "Z", "AA")),
        "reading": ("Table I.B1.5.5", ("L", "M", "N", "O", "P", "Q", "AD", "AE")),
        "science": ("Table I.B1.5.6", ("H", "I", "J", "K", "L", "M", "V", "W")),
    }
    require(data["change_se_basis"] == config["change_se_basis"], "Altered assessment trend error basis")
    with ZipFile(path) as archive:
        sheets = spreadsheet_cells(archive, {v[0] for v in layouts.values()})
    expected_count = 0
    for subject, (sheet, columns) in layouts.items():
        original = sheets[sheet]
        given = {row["row"]: row for row in data["rows"] if row["subject"] == subject}
        index_set = set(range(11, 48)) | set(range(53, 97))
        require(set(given) == index_set, "Assessment study population missing")
        expected_count += len(index_set)
        p_values = []
        changes = []
        for index in sorted(index_set):
            row = given[index]
            label = original[f"A{index}"]
            caution = "linkage" if label.endswith("**") else "sampling" if label.endswith("*") else None
            system = label.rstrip("*").strip()
            require(row["source_label"] == label and row["caution"] == caution, "Assessment caution or system changed")
            require(
                row["system"] == system and row["atlas_region"] == config["systems"][system]
                and row["source_sha256"] == sha and row["sheet"] == sheet
                and row["unit"] == "PISA scale points",
                "Assessment source, system or unit changed",
            )
            require(set(row["cycles"]) == {"2015", "2018", "2022"}, "Assessment cycle labels shifted")
            measurements = [row["cycles"][str(y)] for y in (2015, 2018, 2022)]
            measurements.append(row["2018_to_2022_released"])
            values = []
            errors = []
            for j, measure in enumerate(measurements):
                mean_ref, se_ref = (f"{c}{index}" for c in columns[j * 2:j * 2 + 2])
                require(
                    (measure["source_cell"], measure["se_cell"]) == (mean_ref, se_ref),
                    "Assessment source coordinates shifted",
                )
                for field, missing_key, ref, output in (
                    ("value", "missing", mean_ref, values), ("se", "se_missing", se_ref, errors),
                ):
                    value = original.get(ref)
                    number = value if isinstance(value, float) else None
                    same(measure[field], number, "Released assessment value or standard error changed")
                    require(measure[missing_key] == (None if number is not None else value or "blank"),
                            "Assessment missing code changed")
                    output.append(number)
                value, error = values[-1], errors[-1]
                radius = None if error is None else SE_CRITICAL * error
                for field, sign in (("lower", -1), ("upper", 1)):
                    expected = value + sign * radius if value is not None and radius is not None else None
                    same(measure[field], expected, "Forged assessment interval")
            first, base, end, delta = values
            same(row["2015_to_2018"], base - first if base is not None and first is not None else None,
                 "Early assessment difference changed")
            same(row["2018_to_2022_reconstructed"], end - base if end is not None and base is not None else None,
                 "Reconstructed assessment change differs")
            p = math.erfc(abs(delta / errors[3]) / math.sqrt(2)) if delta is not None and errors[3] else None
            same(row["p_value"], p, "Assessment p-value changed")
            if not caution and p is not None:
                p_values.append((p, index))
            else:
                same(row["q_value"], None, "Ineligible assessment significance claim")
            if delta is not None:
                changes.append((delta, caution, index))
        ordered = sorted(p_values)
        smallest = 1.0
        for rank in range(len(ordered), 0, -1):
            p, index = ordered[rank - 1]
            smallest = min(smallest, p * len(ordered) / rank)
            same(given[index]["q_value"], smallest, "Assessment multiplicity family changed")
        summary = [r for r in data["summary"] if r["subject"] == subject]
        require(len(summary) == 2 and {r["includes_caution"] for r in summary} == {False, True},
                "Missing assessment sensitivity")
        for row in summary:
            members = [(d, idx) for d, mark, idx in changes if row["includes_caution"] or not mark]
            require(row["matched_systems"] == len(members) and row["systems_in_workbook"] == 81,
                    "Assessment summary population changed")
            same(row["median_change_points"], median(d for d, _ in members), "Assessment median changed")
            for field, sign in (("below_2018", -1), ("above_2018", 1)):
                require(row[field] == sum(d * sign > 0 for d, _ in members), "Assessment direction count changed")
            require(row["no_change"] == sum(d == 0 for d, _ in members), "Assessment zero count changed")
            for field, sign in (("adjusted_declines", -1), ("adjusted_increases", 1)):
                count = None if row["includes_caution"] else sum(
                    d * sign > 0 and given[i]["q_value"] is not None and given[i]["q_value"] <= .05
                    for d, i in members
                )
                require(row[field] == count, "Assessment adjusted direction count changed")
    require(len(data["rows"]) == expected_count and len(data["summary"]) == 6, "Added assessment records")
    return expected_count


def verify_instruction(data: dict, config: dict) -> int:
    from .survey_design import MEMBERS

    survey = read_json(ROOT / "configs/survey-inputs.json")["hps_week1"]
    path = ROOT / "data/private-survey" / survey["path"]
    require(digest(path) == survey["sha256"] == data["source_sha256"], "Remote instruction source changed")
    require(data["population"] == config["universe"] and data["replicates"] == 80
            and data["variance_factor"] == 0.05, "Remote instruction population or design changed")
    names = list(config["items"])
    limits = {k: v["maximum"] for k, v in config["time_items"].items()}
    keys = names + [k for name in limits for k in (name, name + "_ZERO", name + "_TOP")]
    persons, values, ages, genders, weights = {}, [], [], [], []
    population, unknown = 0, 0

    def archived_csv(archive, name):
        with archive.open(name) as binary:
            yield from csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8-sig", newline=""))

    with ZipFile(path) as archive:
        require(set(archive.namelist()) == MEMBERS and len(archive.namelist()) == len(MEMBERS),
                "Remote instruction archive inventory")
        require(sum(m.file_size for m in archive.infolist()) < 120_000_000, "Remote instruction archive expansion")
        for row in archived_csv(archive, "pulse2020_puf_01.csv"):
            key = row["SCRAM"], row["WEEK"]
            require(key not in persons and key[1] == "1" and population < 100_000, "Repeated survey record")
            population += 1
            persons[key] = None
            if row["ENROLL1"] == "-88":
                unknown += 1
            if row["ENROLL1"] != "1":
                require(row["ENROLL1"] in {"-88", "-99"}, "Unknown survey eligibility")
                continue
            persons[key] = len(values)
            choices = [{"1": 1.0, "-99": 0.0, "-88": np.nan}[row[k]] for k in names]
            for k, maximum in limits.items():
                value = float(row[k])
                if value in {-99, -88}:
                    choices += [np.nan] * 3
                else:
                    require(0 <= value <= maximum, "Remote instruction hours invalid")
                    choices += [value, float(value == 0), float(value == maximum)]
            values.append(choices)
            ages.append(2020 - int(row["TBIRTH_YEAR"]))
            genders.append({"1": "Male", "2": "Female"}[row["EGENDER"]])
            weights.append(float(row["PWEIGHT"]))
        weight_matrix = np.empty((len(values), 81))
        weight_matrix[:, 0] = weights
        for row in archived_csv(archive, "pulse2020_repwgt_puf_01.csv"):
            key = row["SCRAM"], row["WEEK"]
            require(key in persons, "Missing local survey join partner")
            index = persons.pop(key)
            if index is not None:
                weight_matrix[index, 1:] = [float(row[f"PWEIGHT{i}"]) for i in range(1, 81)]
    require(not persons and population == 74_413 == data["respondent_rows"]
            and unknown == data["unknown_eligibility_rows"], "Remote instruction roster changed")
    require(np.isfinite(weight_matrix).all() and (weight_matrix >= 0).all()
            and (weight_matrix[:, 0] > 0).all(), "Invalid remote instruction design weights")
    values, ages, genders = np.array(values), np.array(ages), np.array(genders)
    groups = {
        "All eligible adults": ages > 0, "Male": genders == "Male", "Female": genders == "Female",
        **{f"Age {a} to {b}" if b < 120 else f"Age {a}+": (ages >= a) & (ages <= b)
           for a, b in config["age_bands"]},
    }
    actual = {(row["group"], row["metric"]): row for row in data["rows"]}
    require(len(actual) == len(data["rows"]) == len(groups) * len(keys), "Remote instruction cells changed")
    for group, mask in groups.items():
        adult_total = float(weight_matrix[mask, 0].sum())
        for j, key in enumerate(keys):
            row = actual[group, key]
            valid = mask & np.isfinite(values[:, j])
            obs = values[valid, j]
            w = weight_matrix[valid]
            denom = w.sum(axis=0)
            binary = key not in limits
            maximum = 1 if binary else limits[key]
            scale = 100 if binary else 1
            require(row["population"] == config["universe"] and row["source_hash"] == survey["sha256"]
                    and row["unit"] == ("percent of eligible adults" if binary else "reported hours"),
                    "Remote instruction denominator unit changed")
            withheld = len(obs) < 100 or (denom <= 0).any() or (
                binary and min((obs == 0).sum(), (obs == 1).sum()) < 10
            )
            expected = {}
            if not withheld:
                ratio = (w.T @ obs) / denom
                se = float(np.linalg.norm(ratio[1:] - ratio[0]) / math.sqrt(20))
                withheld = ratio[0] != 0 and se / ratio[0] > .3
                value = float(ratio[0])
                missing = max(0, adult_total - denom[0])
                expected = {
                    "value": value * scale, "se": se * scale,
                    "lower": max(0, value - SE_CRITICAL * se) * scale,
                    "upper": min(maximum, value + SE_CRITICAL * se) * scale,
                    "denominator": float(denom[0]), "complete_respondents": len(obs),
                    "eligible_respondents": int(mask.sum()),
                    "kish_effective_n": float(denom[0] ** 2 / (w[:, 0] @ w[:, 0])),
                    "weighted_item_missing_fraction": missing / adult_total,
                    "item_missing_lower": float(ratio[0] * denom[0] / adult_total) * scale,
                    "item_missing_upper": float((ratio[0] * denom[0] + maximum * missing) / adult_total) * scale,
                }
            require(row["suppressed"] == bool(withheld), "Remote instruction suppression changed")
            if withheld:
                for field in ("value", "se", "lower", "upper", "denominator", "complete_respondents",
                              "eligible_respondents", "kish_effective_n", "weighted_item_missing_fraction",
                              "item_missing_lower", "item_missing_upper"):
                    same(row[field], None, "Remote instruction suppressed field disclosed")
            else:
                for field, value in expected.items():
                    same(row[field], value, "Remote instruction replicate or adult denominator mismatch")
    return len(actual)


def verify_hours(path: Path, data: dict, config: dict, annual: dict, sha: str) -> int:
    by_year = {}
    noncountry = 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        for record in csv.DictReader(f):
            require(record["HOURS_TYPE"] == "ACTUAL" and record["UNIT_MEASURE"] == "H_Y_PS"
                    and record["WORKER_STATUS"] == "_T" and record["LABOUR_FORCE_STATUS"] == "EMP"
                    and record["WORK_PERIOD"] == "A" and record["JOB_COVERAGE"] == "_T",
                    "Hours source definition or population changed")
            country, year = record["REF_AREA"], int(record["TIME_PERIOD"])
            if country == "OECD":
                noncountry += 1
                continue
            require((country, year) not in by_year, "Duplicate hours country-year")
            hours = record["OBS_VALUE"]
            by_year[country, year] = (float(hours) if hours else None, record["OBS_STATUS"])
    expected = {(c, y) for c, _ in by_year for y in (2020, 2022)}
    require(data["status"] == "acquired" and data["observations"] == len(by_year)
            and data["source_sha256"] == sha and data["unit"] == config["unit"]
            and data["excluded_observations"] == {"OECD aggregate": noncountry},
            "Hours study provenance or coverage mismatch")
    actual = {(r["region"], r["target_year"]): r for r in data["rows"]}
    require(set(actual) == expected and len(actual) == len(data["rows"]), "Hours matched cohort changed")
    for (country, year), row in actual.items():
        panel = [by_year.get((country, y), (None, None)) for y in range(2019, year + 1)]
        base, target = panel[0][0], panel[-1][0]
        good = all(value is not None and flag in config["admissible_statuses"] for value, flag in panel)
        require(row["baseline_year"] == 2019 and row["unit"] == config["unit"]
                and row["source_sha256"] == sha and row["cohort"] == "total employment",
                "Hours definition or denominator substituted")
        require(row["flag_history"] == [flag for _, flag in panel]
                and bool(row["comparison_exclusions"]) == (not good), "Hours break or incomplete window ignored")
        same(row["baseline_hours"], base, "Hours baseline value changed")
        same(row["target_hours"], target, "Hours endpoint value changed")
        same(row["hours_index"], 100 * target / base if good else None, "Hours index or eligibility changed")
        same(row["change_hours"], target - base if good else None, "Hours change differs from source")
        gdp_start, gdp_end = annual.get((country, "gdp", 2019)), annual.get((country, "gdp", year))
        gdp = 100 * gdp_end / gdp_start if gdp_start and gdp_end else None
        same(row["gdp_per_person_index"], gdp, "Hours and GDP merge population changed")
        require(row["gdp_match"] == (gdp is not None and good), "Hours GDP episode eligibility changed")
        same(row["standard_error"], None, "Invented hours standard error")
    require(len(data["summary"]) == 2 and {r["year"] for r in data["summary"]} == {2020, 2022},
            "Hours summary population changed")
    for row in data["summary"]:
        records = [x for (_, year), x in actual.items() if year == row["year"]]
        matched = [x for x in records if x["hours_index"] is not None]
        values = [x["hours_index"] - 100 for x in matched]
        joint = [x for x in matched if x["gdp_match"]]
        require(row["countries"] == len(matched) and row["excluded"] == len(records) - len(matched)
                and row["gdp_matches"] == len(joint), "Hours summary count changed")
        require(row["below_2019_hours"] == sum(x < 0 for x in values)
                and row["above_2019_hours"] == sum(x > 0 for x in values), "Hours summary direction changed")
        require(row["diverging_hours_and_gdp"] == sum(
            (x["hours_index"] - 100) * (x["gdp_per_person_index"] - 100) < 0 for x in joint
        ), "Hours and GDP direction changed")
        same(row["median_hours_change_percent"], median(values) if len(values) >= 5 else None,
             "Hours summary median changed")
        require(row["range_hours_change_percent"] == ([min(values), max(values)] if len(values) >= 5 else None),
                "Hours summary range changed")
    return len(actual)


def verify_measurement(bundle: Path, annual: dict, source: str) -> dict:
    config_file = ROOT / "configs/measurement-v4.json"
    config = read_json(config_file)
    pins = {**config["sources"], **read_json(ROOT / "configs/measurement-hours.json")}
    data = read_json(bundle / "measurement-v4.json")
    require(data["source"] == source and data["definition_sha256"] == digest(config_file)
            and data["protocol"] == config["version"] and data["sources"] == pins,
            "Measurement artifacts differ from registered source")
    originals = {}
    for identity, metadata in pins.items():
        path = contained(bundle, f"measurement-raw/{identity}.{metadata['format']}")
        require(digest(path) == metadata["sha256"] and path.stat().st_size == metadata["bytes"],
                "Measurement source bytes mismatch")
        originals[identity] = path
    learning = verify_learning(originals["pisa_2022_b15"], data["learning"], config["pisa"],
                               pins["pisa_2022_b15"]["sha256"])
    hours = verify_hours(originals["oecd_annual_hours"], data["hours"], config["hours"], annual,
                         pins["oecd_annual_hours"]["sha256"])
    instruction = verify_instruction(data["remote_instruction"], config["census"])
    return {"learning_rows": learning, "hours_rows": hours, "instruction_aggregates": instruction}
