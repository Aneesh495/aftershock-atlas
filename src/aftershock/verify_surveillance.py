"""Replay state rollups from raw CSV using independent DuckDB group and window queries."""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import duckdb

from .io import ROOT, digest, read_json
from .verification import require


def query_by_week(db: duckdb.DuckDBPyConnection, sql: str) -> dict:
    result = db.execute(sql)
    columns = [column[0] for column in result.description]
    return {(row[0], row[1].isoformat()): dict(zip(columns[2:], row[2:], strict=True))
            for row in result.fetchall()}


def same(actual: object, expected: object, identity: str) -> None:
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and set(actual) == set(expected), f"Surveillance shape changed: {identity}")
        for key in expected:
            same(actual[key], expected[key], f"{identity}.{key}")
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), f"Surveillance count changed: {identity}")
        for row, target in zip(actual, expected, strict=True):
            same(row, target, identity)
    elif type(expected) is float:
        require(type(actual) in {float, int} and math.isclose(actual, expected, abs_tol=1e-9, rel_tol=1e-12),
                f"Surveillance value changed: {identity}")
    else:
        require(type(actual) is type(expected) and actual == expected, f"Surveillance value changed: {identity}")


def load_reports(db: duckdb.DuckDBPyConnection, raw: Path, definitions: dict, pins: dict) -> None:
    db.execute("SET threads = 2")
    db.execute("SET memory_limit = '450MB'")
    db.execute("SET temp_directory = ''")
    for domain, scope in definitions["fields"].items():
        key = f"v5_{domain}"
        paths = {}
        for suffix in ("rows", "count"):
            pin = pins[f"{key}_{suffix}"]
            path = raw / pin["path"]
            require(path.stat().st_size == pin["bytes"] and digest(path) == pin["sha256"],
                    f"Surveillance source byte identity changed: {domain}")
            paths[suffix] = path
        statement = f"""CREATE TEMP TABLE {domain} AS
            SELECT {scope['jurisdiction']} AS region_id, cast(date as DATE) AS day,
            cast(date_trunc('week',cast(date as DATE)) AS DATE) AS week_start, *
            FROM read_csv(?,header=true, all_varchar=true)"""
        db.execute(statement, [str(paths["rows"])])
        count, first, last = db.execute(f"SELECT count(*),min(day),max(day) FROM {domain}").fetchone()
        source_count, = read_json(paths["count"])
        require(
            (count, first.isoformat(), last.isoformat()) ==
            (int(source_count["row_count"]), source_count["earliest"][:10], source_count["latest"][:10]),
            f"Surveillance count endpoint disagrees: {domain}",
        )
        codes = {x[0] for x in db.execute(f"SELECT DISTINCT region_id FROM {domain}").fetchall()}
        require(codes <= set(definitions["state_fips"]) and
                scope["first"] <= first.isoformat() <= last.isoformat() <= scope["last"],
                f"Surveillance cohort changed: {domain}")
        domains = "region_id,day,overall_outcome" if domain == "testing" else "region_id,day"
        duplicate = db.execute(f"""SELECT 1 FROM {domain}
            GROUP BY {domains} HAVING count(*) <> 1 LIMIT 1""").fetchone()
        require(duplicate is None, f"Duplicate region-day source report: {domain}")
    labels = db.execute("SELECT DISTINCT region_id,lpad(state_fips,2,'0'),overall_outcome FROM testing").fetchall()
    require(all(definitions["state_fips"][r] == f and o in {"Positive", "Negative", "Inconclusive"}
                for r, f, o in labels), "PCR source jurisdiction or outcome classification changed")


def hospital_checks(db: duckdb.DuckDBPyConnection) -> dict:
    levels = query_by_week(db, """
        WITH parsed AS (
          SELECT region_id,week_start,
            previous_day_admission_adult_covid_confirmed::BIGINT AS admitted,
            staffed_icu_adult_patients_confirmed_covid::BIGINT AS confirmed,
            staffed_icu_adult_patients_confirmed_covid_coverage::BIGINT AS contributors
          FROM hospital
        )
        SELECT region_id,week_start,count(*) AS reports,
          count(*) FILTER (WHERE admitted>=0) AS admission_days,
          sum(admitted) FILTER (WHERE admitted>=0) AS admission_reported,
          count(*) FILTER (WHERE confirmed>=0 AND contributors>0) AS icu_days,
          avg(confirmed) FILTER (WHERE confirmed>=0 AND contributors>0) AS icu_reported,
          min(contributors) FILTER (WHERE confirmed>=0 AND contributors>0) AS icu_minimum
        FROM parsed GROUP BY region_id,week_start
    """)
    paired = {}
    for prefix, name in (
        ("adult_icu_bed_utilization", "all_cause_adult_icu_occupancy"),
        ("adult_icu_bed_covid_utilization", "confirmed_or_suspected_adult_icu_occupancy"),
    ):
        paired[name] = query_by_week(db, f"""
            WITH parsed AS (
              SELECT region_id,week_start,
                {prefix}_numerator::BIGINT AS numerator,
                {prefix}_denominator::BIGINT AS denominator,
                {prefix}_coverage::BIGINT AS coverage,
                numerator BETWEEN 0 AND denominator AND denominator>0 AND coverage>0 AS valid
              FROM hospital
            )
            SELECT region_id,week_start,count(*) FILTER (WHERE valid) AS paired_days,
              sum(numerator) FILTER (WHERE valid) AS occupied_bed_days,
              sum(denominator) FILTER (WHERE valid) AS staffed_bed_days,
              min(coverage) FILTER (WHERE valid) AS minimum_contributors,
              count(*) FILTER (WHERE numerator>denominator AND denominator>=0) AS over_capacity_days,
              CASE WHEN count(*) FILTER (WHERE valid)=7 THEN
                100.0 * (sum(numerator) FILTER (WHERE valid))/(sum(denominator) FILTER (WHERE valid))
              END AS weekly_percent
            FROM parsed GROUP BY region_id,week_start
        """)
    output = {}
    for key, row in levels.items():
        output[key] = {
            "reports": row["reports"],
            "confirmed_adult_admissions": {
                "days": row["admission_days"], "reported_total": row["admission_reported"],
                "weekly_total": row["admission_reported"] if row["admission_days"] == 7 else None,
            },
            "confirmed_adult_icu_patients": {
                "days": row["icu_days"], "reported_mean": row["icu_reported"],
                "weekly_mean": row["icu_reported"] if row["icu_days"] == 7 else None,
                "minimum_contributors": row["icu_minimum"],
            },
            **{name: cells[key] for name, cells in paired.items()},
        }
    return output


def testing_checks(db: duckdb.DuckDBPyConnection) -> dict:
    groups = {}
    for category in ("Positive", "Negative", "Inconclusive"):
        groups[category.lower()] = query_by_week(db, f"""
            WITH parsed AS (
              SELECT region_id,week_start,day,new_results_reported::BIGINT AS results,
                total_results_reported::BIGINT AS cumulative
              FROM testing WHERE overall_outcome='{category}'
            )
            SELECT region_id,week_start,count(results) AS days,
              sum(results) AS reported_total,
              CASE WHEN count(results)=7 THEN sum(results) END AS weekly_total,
              max(day) FILTER (WHERE cumulative>=0)::VARCHAR AS latest_total_date,
              arg_max(cumulative,day) FILTER (WHERE cumulative>=0) AS latest_total
            FROM parsed GROUP BY region_id,week_start
        """)
    totals = query_by_week(db, """
        SELECT region_id,week_start,count(DISTINCT day) AS reports,
          count(*) FILTER(WHERE new_results_reported::BIGINT<0) AS negative_result_corrections
        FROM testing GROUP BY region_id,week_start
    """)
    empty = {"days": 0, "reported_total": None, "weekly_total": None,
             "latest_total_date": None, "latest_total": None}
    for population, row in totals.items():
        cumulative = {}
        for name, group in groups.items():
            values = group.get(population, empty)
            row[name] = {k: values[k] for k in ("days", "reported_total", "weekly_total")}
            if values["latest_total_date"] is not None:
                cumulative[name] = {"date": values["latest_total_date"], "count": values["latest_total"]}
        p, n = row["positive"]["weekly_total"], row["negative"]["weekly_total"]
        denominator = p + n if not row["negative_result_corrections"] and p is not None and n is not None else None
        row.update(latest_cumulative_results=cumulative, determinate_results=denominator,
                   weekly_positivity_percent=100.0 * p / denominator if denominator else None)
    return totals


def vaccination_checks(db: duckdb.DuckDBPyConnection) -> dict:
    db.execute("""
        CREATE TEMP VIEW vaccination_reports AS
          WITH parsed AS (
            SELECT region_id,day,week_start,
              CASE WHEN series_complete_yes::BIGINT>=0 THEN series_complete_yes::BIGINT END AS persons,
              CASE WHEN administered::BIGINT>=0 THEN administered::BIGINT END AS doses,
              series_complete_pop_pct::DOUBLE AS percent
            FROM vaccination
          )
          SELECT *,
            lag(day) OVER (PARTITION BY region_id ORDER BY day) AS earlier,
            persons-lag(persons) OVER (PARTITION BY region_id ORDER BY day) AS signed_change
          FROM parsed
    """)
    return query_by_week(db, """
        SELECT region_id,week_start,count(*) AS reports,
          arg_max(struct_pack(
            report_date:=day::VARCHAR, previous_report_date:=earlier::VARCHAR,
            days_since_previous_report:=day-earlier, resident_primary_series_complete:=persons,
            provider_coverage_percent:=percent,
            matches_documented_cap:=coalesce(percent IN (95.0,99.9),false),
            administered_doses_in_jurisdiction:=doses, signed_primary_series_update:=signed_change
          ),day) AS latest_report,
          count(*) FILTER (WHERE signed_change<0) AS negative_completion_updates,
          coalesce(list(struct_pack(
            report_date:=day::VARCHAR, previous_report_date:=earlier::VARCHAR,
            signed_primary_series_update:=signed_change
          ) ORDER BY day) FILTER (WHERE signed_change<0),[]) AS completion_corrections
        FROM vaccination_reports GROUP BY region_id,week_start
    """)


def verify_surveillance(artifact: dict, raw: Path, expected_source: str) -> dict:
    config_path = ROOT / "configs/surveillance-v5.json"
    pins_path = ROOT / "configs/surveillance-inputs.json"
    config, pins = read_json(config_path), read_json(pins_path)
    require(artifact["source"] == expected_source and artifact["definition_sha256"] == digest(config_path)
            and artifact["pins_sha256"] == digest(pins_path), "State surveillance source identity mismatch")
    same(artifact["registry"], config["fields"], "timing or denominator metadata")
    same(artifact["inputs"], {k: {"bytes": v["bytes"], "sha256": v["sha256"]} for k, v in pins.items()},
         "input manifest")
    with duckdb.connect() as db:
        load_reports(db, raw, config, pins)
        replay = {
            "hospital": hospital_checks(db),
            "testing": testing_checks(db),
            "vaccination": vaccination_checks(db),
        }
    empty_flow = {"days": 0, "reported_total": None, "weekly_total": None}
    empty_beds = {"paired_days": 0, "occupied_bed_days": None, "staffed_bed_days": None,
                  "minimum_contributors": None, "over_capacity_days": 0, "weekly_percent": None}
    empty = {
        "hospital": {
            "reports": 0,
            "confirmed_adult_admissions": empty_flow,
            "confirmed_adult_icu_patients": {"days": 0, "reported_mean": None, "weekly_mean": None,
                                             "minimum_contributors": None},
            "all_cause_adult_icu_occupancy": empty_beds,
            "confirmed_or_suspected_adult_icu_occupancy": empty_beds,
        },
        "testing": {
            "reports": 0, "positive": empty_flow, "negative": empty_flow, "inconclusive": empty_flow,
            "latest_cumulative_results": {}, "negative_result_corrections": 0,
            "determinate_results": None, "weekly_positivity_percent": None,
        },
        "vaccination": {
            "reports": 0, "latest_report": None, "negative_completion_updates": 0, "completion_corrections": [],
        },
    }
    summary = {}
    require(set(artifact["states"]) == set(config["state_fips"]), "State surveillance state inventory mismatch")
    for kind, scope in config["fields"].items():
        first, last = [date.fromisoformat(scope[field]) for field in ("first", "last")]
        monday = first - timedelta(days=first.isoweekday() - 1)
        weeks = [(monday + timedelta(days=i)).isoformat() for i in range(0, (last - monday).days + 1, 7)]
        group = replay[kind]
        summary[kind] = {
            "weeks": len(weeks) * len(artifact["states"]),
            "with_reports": len(group),
            "with_seven_report_dates": sum(row["reports"] == 7 for row in group.values()),
        }
        for state, data in artifact["states"].items():
            require(len(data[kind]) == len(weeks), f"Weekly surveillance calendar changed: {state}.{kind}")
            for week, row in zip(weeks, data[kind], strict=True):
                expected = {"week_start": week, **group.get((state, week), empty[kind])}
                same(row, expected, f"{state}.{kind}.{week}")
    same(artifact["summary"], summary, "coverage summary")
    return {"states": len(artifact["states"]), "state_week_rows": sum(r["weeks"] for r in summary.values()),
            "summary": summary}
