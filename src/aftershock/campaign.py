"""Source-frozen bounded campaign orchestration and actual verifier negative controls."""
from __future__ import annotations

import csv
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from .io import ROOT, append_json, digest, now, read_json, source_commit, write_json
from .panel import connect
from .resources import doctor, usage
from .verification import trusted_inputs, verify_bundle


def make_manifest(bundle: Path) -> None:
    files = {str(p.relative_to(bundle)): {"sha256": digest(p), "bytes": p.stat().st_size}
             for p in sorted(bundle.rglob("*")) if p.is_file() and p.name not in {"MANIFEST.json", "VERIFICATION.json"}}
    write_json(bundle / "MANIFEST.json", {"schema_version": 1, "files": files})


def gates(bundle: Path | None = None) -> list[dict]:
    panel = read_json(ROOT / "data/panel/manifest.json")
    fit = read_json(ROOT / "data/results/fit.json")
    studies = read_json(ROOT / "data/results/studies.json")
    coverage = {r["metric"]: r for r in panel["coverage"]}
    definitions = [
        ("G01", "passed", "22 core, 2 survey and 43 historical input partitions; metric-level coverage and separate rights", "DATASETS.json"),
        ("G02", "blocked", "Official archive-month editions present; original cell release-day and historical territory validation incomplete", "observations.csv"),
        ("G03", "passed", "Independent source-parser, matched annual denominators and direct age-standardization replay", "age-replay.json"),
        ("G04", "passed", f"{coverage['covid_deaths']['countries']} surveillance countries; real multiyear health and economic panel", "observations.csv"),
        ("G05", "passed", "WHO 2022 and 2023 modeled excess releases, input support and changed age bands retained", "excess.json"),
        ("G06", "blocked", "Week 1 replicate weights and nonresponse sensitivity replayed; later-wave design auditing remains incomplete", "surveys.json"),
        ("G07", "blocked", "GDP and enrollment run; hours, remote instruction and learning assessments absent", "studies.json"),
        ("G08", "unverified", "Provider-released US subgroup estimates retain labels and suppression; independent subgroup denominator audit incomplete", "surveys.json"),
        ("G09", "passed", "Real HGI technical harmonization and archived CDC weighted lineage estimates; shared sample and LD limits explicit", "genetics.json"),
        ("G10", "blocked", f"{fit['completed_configurations']} original configurations plus 66 archive configurations; release-day proof and pandemic calibration remain incomplete", "history-fit.json"),
        ("G11", "passed", "Real candidate group-time analyses, pretrends, pseudo-onsets and unsupported cells", "causal.json"),
        ("G12", "blocked", f"{studies['count']} executed tables, {studies['partial_support']} with incomplete outcome or design support", "studies.json"),
        ("G13", "unverified", "Atlas implementation exists; interactive source-frozen final walkthrough must be reviewed", "browser-checks.json"),
        ("G14", "passed", "Shared disclosure boundary, provider flags and export checks", "surveys.json"),
        ("G15", "passed", "Bounded acquisitions, checkpoint resume and measured storage accounting", "ENVIRONMENT.json"),
        ("G16", "unverified", "Requires recorded semantic negative-control subprocesses on this exact source", "negative-controls.json"),
    ]
    rows = [{"gate": g, "status": status, "reason": reason, "artifact": artifact} for g, status, reason, artifact in definitions]
    if bundle is not None and (bundle / "negative-controls.json").exists():
        controls = read_json(bundle / "negative-controls.json")
        expected_source = read_json(bundle / "START.json")["source"]
        if controls["source"] == expected_source and controls["rejected"] == len(controls["controls"]) >= 19:
            row = next(r for r in rows if r["gate"] == "G16")
            row.update(status="passed", reason="19 actual source-matched semantic and structural tamper subprocesses rejected")
    return rows


def execute_stage(bundle: Path, name: str, command: list[str], timeout: int = 600) -> None:
    started = time.monotonic()
    log = bundle / "logs" / f"{name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["OPENBLAS_NUM_THREADS"] = "1"
    environment["OMP_NUM_THREADS"] = "1"
    environment["PYTHONPATH"] = str(ROOT / "src")
    usage(200_000_000)
    code = 124
    with log.open("w") as stream:
        try:
            completed = subprocess.run(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
            code = completed.returncode
        finally:
            append_json(bundle / "COMMANDS.jsonl", {"stage": name, "argv": command, "exit": code,
                        "elapsed_seconds": time.monotonic() - started, "finished_at": now()})
    if code:
        raise RuntimeError(f"Campaign stage {name} failed ({code}); see {log}")
    print(f"completed {name} in {time.monotonic()-started:.2f}s", flush=True)


def assemble(bundle: Path, source: str, profile: str) -> None:
    results = ROOT / "data/results"
    for name in ("predictions", "fit", "age-replay", "studies", "genetics", "causal", "surveys", "excess", "subnational", "lineages", "mobility", "scenarios", "survey-design", "dynamic", "dynamic-predictions"):
        shutil.copyfile(results / f"{name}.json", bundle / f"{name}.json")
    shutil.copytree(ROOT / "data/models", bundle / "models", ignore=shutil.ignore_patterns("resume.npz", "history.json"))
    write_json(bundle / "SURVEY_INPUTS.json", read_json(ROOT / "configs/survey-inputs.json"))
    assemble_history(bundle)
    source_files = trusted_inputs(source)
    write_json(bundle / "SOURCE_INPUTS.json", {"commit": source, "files": source_files, "protocol_sha256": digest(ROOT / "docs/EXPERIMENT_PLAN.md")})
    sources = read_json(ROOT / "configs/data-inputs.json")
    for key, record in sources.items():
        if record["status"] == "acquired":
            origin = ROOT / "data/raw" / record["path"]
            destination = bundle / "raw" / (key + "." + record["format"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, destination)
            record["bundle_path"] = str(destination.relative_to(bundle))
    write_json(bundle / "DATASETS.json", {"sources": sources, "panel": read_json(ROOT / "data/panel/manifest.json")})
    with connect() as db:
        result = db.execute("""SELECT * FROM observations WHERE frequency='annual' OR metric IN ('covid_cases','covid_deaths') ORDER BY region,metric,event_start""")
        columns = [c[0] for c in result.description]
        with (bundle / "observations.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            while rows := result.fetchmany(8192):
                writer.writerows(rows)
    environment = doctor()
    environment["dependencies"] = {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "pyarrow", "duckdb", "pycountry")}
    write_json(bundle / "ENVIRONMENT.json", environment)
    keys = read_json(ROOT / "data/models/replay-keys.json")
    eligible = [i for i, k in enumerate(keys) if 2019 <= k["target_year"] <= 2024]
    write_json(bundle / "PROBES.json", {"model_indices": eligible, "selection": "all eligible test-row identities in frozen country/year order"})
    browser = ROOT / "docs/media/browser-checks.json"
    if browser.exists():
        shutil.copyfile(browser, bundle / "browser-checks.json")
    write_json(bundle / "REQUIREMENTS.json", {"gates": gates(), "profile": profile})
    write_json(bundle / "ACCEPTANCE.json", {"profile": profile, "source": source, "gates": gates(),
               "requested": {"trained_seeds": 3, "minimum_configurations": 30},
               "completed": {"trained_seeds": 3, "configurations": read_json(results / "fit.json")["completed_configurations"]},
               "configuration_exercises": {"retrospective_core": 60, "exploratory_dynamic": 6, "historical_v3": 66},
               "full_acceptance": False})
    make_manifest(bundle)


def assemble_history(bundle: Path) -> None:
    """Include public aggregate archive bytes, never respondent-level inputs."""
    for name in ("history-fit", "history-revisions", "history-anchors", "history-sensitivity"):
        shutil.copyfile(ROOT / f"data/results/{name}.json", bundle / f"{name}.json")
    shutil.copytree(ROOT / "data/results/history-predictions", bundle / "history-predictions")
    shutil.copyfile(ROOT / "data/history/manifest.json", bundle / "history-manifest.json")
    shutil.copyfile(ROOT / "data/history/observations.parquet", bundle / "history-observations.parquet")
    sources = read_json(ROOT / "configs/history-inputs.json")
    for key, record in sources.items():
        origin = ROOT / "data/history/raw" / record["path"]
        destination = bundle / "history-raw" / (key + ".json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Immutable source bytes share storage; all bundle paths remain self-contained.
        try:
            os.link(origin, destination)
        except OSError:
            usage(record["bytes"])
            shutil.copyfile(origin, destination)
        record["bundle_path"] = str(destination.relative_to(bundle))
    write_json(bundle / "HISTORY_INPUTS.json", sources)


def negative_controls(bundle: Path, source: str) -> dict:
    """Each rehashed semantic mutation invokes the actual verifier in a new process."""
    usage(600_000_000)
    controls_root = ROOT / ".agent-local/negative-controls"
    controls_root.mkdir(parents=True, exist_ok=True)
    receipts = []
    def mutate(name: str, relative: str, transform, expected_reason: str, rehash: bool = True):
        destination = controls_root / (bundle.name + "-" + name)
        if destination.exists():
            raise ValueError("Negative-control identity collision")
        # Copy mutable records; immutable raw inputs and model files are hard-linked read-only in practice.
        shutil.copytree(bundle, destination, copy_function=os.link)
        target = destination / relative
        payload = target.read_bytes()
        target.unlink()
        changed = transform(payload)
        if changed is not None:
            target.write_bytes(changed)
        if relative.startswith("history-predictions/") and rehash:
            fit_path = destination / "history-fit.json"
            fit = read_json(fit_path)
            fit["prediction_files"][Path(relative).stem].update(sha256=digest(target), bytes=target.stat().st_size)
            write_json(fit_path, fit)
        manifest_path = destination / "MANIFEST.json"
        manifest_path.unlink()
        if rehash:
            make_manifest(destination)
        else:
            shutil.copyfile(bundle / "MANIFEST.json", manifest_path)
        command = [sys.executable, "-m", "aftershock.cli", "verify", "--evidence", str(destination), "--expected-source", source]
        process = subprocess.run(command, capture_output=True, text=True, cwd=ROOT, timeout=180)
        detail = (process.stderr + process.stdout).strip()[-3000:]
        require_reject = process.returncode != 0 and expected_reason in detail
        if not require_reject:
            raise ValueError("Verifier failed to reject for the intended reason: " + name + ": " + detail)
        receipts.append({"name": name, "command": command, "exit": process.returncode, "reason": detail, "rehashes_recomputed": rehash})
        # Recipes are frozen in source; preserve actual invocations and rejection text.
        write_json(controls_root / (destination.name + ".receipt.json"), receipts[-1])
        shutil.rmtree(destination)
    def json_change(action):
        def change(payload):
            import json
            value = json.loads(payload)
            action(value)
            return json.dumps(value, allow_nan=False).encode()
        return change
    def forged_vintage(payload):
        rows = payload.decode().splitlines()
        header = next(csv.reader([rows[0]]))
        row = next(csv.reader([rows[1]]))
        row[header.index("available_at")] = "2019-01-01T00:00:00+00:00"
        import io
        out = io.StringIO()
        csv.writer(out).writerows([header, row])
        return (out.getvalue() + "\n".join(rows[2:]) + "\n").encode()
    mutate("forged-vintage", "observations.csv", forged_vintage, "Forged vintage")
    mutate("duplicate-population", "observations.csv", lambda b: b + b.splitlines(keepends=True)[1], "Duplicate measurement population")
    mutate("future-label", "predictions.json", json_change(lambda a: a[0].update(feature_last_year=a[0]["target_year"])), "Future feature label")
    mutate("invalid-effect-sign", "genetics.json", json_change(lambda a: a["representatives"][0].update(a2_beta=-a["representatives"][0]["a2_beta"])), "Invalid genetic effect sign")
    mutate("shifted-placebo", "causal.json", json_change(lambda a: a["pseudo_onsets"][0].update(baseline_year=2000)), "Shifted placebo")
    mutate("shared-sample-reclassification", "genetics.json", json_change(lambda a: a.update(independent_replication=True)), "Shared-sample genetics")
    mutate("survey-category", "survey-design.json", json_change(lambda a: a["rows"][12].update(group="Universal ancestral category")), "Survey population reclassified")
    mutate("survey-variance-factor", "survey-design.json", json_change(lambda a: a.update(variance_factor=1 / 80)), "Invalid survey variance factor")
    mutate("survey-denominator", "survey-design.json", json_change(lambda a: a["rows"][0].update(denominator=1.)), "Survey weighted denominator mismatch")
    mutate("dynamic-parameters", "dynamic.json", json_change(lambda a: a["fits"][0]["chosen"]["parameters"].__setitem__(0, 10.)), "Dynamic training likelihood replay mismatch")
    mutate("later-archive", "history-predictions/employment.json", json_change(lambda a: a[0].update(edition="202312", edition_available_at="2023-12-31T23:59:59+00:00")), "Historical edition follows origin")
    mutate("forged-archive-bound", "history-predictions/employment.json", json_change(lambda a: a[0].update(edition_available_at="2010-01-01T00:00:00+00:00")), "Forged historical edition bound")
    mutate("changed-gdp-anchor", "history-anchors.json", json_change(lambda a: next(r for r in a if r["raw_2010"] is not None).update(raw_2010=1.)), "Historical GDP anchor detached from raw edition")
    def future_history_feature(payload):
        import io
        with np.load(io.BytesIO(payload), allow_pickle=False) as saved:
            arrays = {k: saved[k].copy() for k in saved.files}
        row = int(np.where(arrays["test"] & arrays["mask"][:, 0])[0][0])
        column = 18
        center = np.nanmean(arrays["raw"][arrays["train"]], axis=0)[column]
        scale = max(float(np.nanstd(arrays["raw"][arrays["train"]], axis=0)[column]), 1e-4)
        future = arrays["target"][row, 0] + arrays["base"][row, 0]
        arrays["raw"][row, column] = future
        arrays["x"][row, column] = (future - center) / scale
        output = io.BytesIO()
        np.savez_compressed(output, **arrays)
        return output.getvalue()
    mutate("future-history-feature", "models/historical-v3/replay-inputs.npz", future_history_feature, "Historical replay inputs differ from raw archives")
    def promote_full_scope(record):
        record.update(profile="full", full_acceptance=True)
        for gate in record["gates"]:
            gate["status"] = "passed"
    mutate("forged-full-pass", "ACCEPTANCE.json", json_change(promote_full_scope), "Full scope claims exceed source-supported capabilities")
    mutate("corruption", "genetics.json", lambda b: b + b" ", "Artifact checksum", rehash=False)
    mutate("missing-artifact", "genetics.json", lambda b: None, "Unlisted or missing", rehash=False)
    mutate("source-mismatch", "SOURCE_INPUTS.json", json_change(lambda a: a.update(commit="0" * 40)), "Source commit mismatch")
    def bad_checkpoint(payload):
        import io
        with np.load(io.BytesIO(payload), allow_pickle=False) as saved:
            arrays = {k: saved[k].copy() for k in saved.files}
        arrays["p_w2"][0, 0] += 1
        stream = io.BytesIO()
        np.savez_compressed(stream, **arrays)
        return stream.getvalue()
    mutate("failed-replay", "models/seed-11/best.npz", bad_checkpoint, "Saved model mean replay failed")
    result = {"controls": receipts, "rejected": len(receipts), "source": source}
    write_json(bundle / "negative-controls.json", result)
    make_manifest(bundle)
    return result


def acceptance(run_id: str, profile: str) -> dict:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", run_id):
        raise ValueError("Invalid run identity")
    usage(500_000_000)
    bundle = ROOT / "evidence" / run_id
    bundle.mkdir(parents=True, exist_ok=False)
    source = source_commit()
    write_json(bundle / "START.json", {"source": source, "profile": profile, "at": now()})
    try:
        for name in ("panel", "history-panel", "fit", "dynamic", "history-fit", "forecasts", "causal", "studies", "history-atlas", "atlas"):
            execute_stage(bundle, name, [sys.executable, "-m", "aftershock.cli", name])
        execute_stage(bundle, "correctness", [sys.executable, "-m", "pytest", "-q"])
        assemble(bundle, source, profile)
        # Execute independent checks even when unrelated domain coverage remains incomplete.
        verify_bundle(bundle, source, require_domain_gates=False)
        negative_controls(bundle, source)
        current_gates = gates(bundle)
        requirements = read_json(bundle / "REQUIREMENTS.json")
        requirements["gates"] = current_gates
        write_json(bundle / "REQUIREMENTS.json", requirements)
        acceptance_record = read_json(bundle / "ACCEPTANCE.json")
        acceptance_record["gates"] = current_gates
        write_json(bundle / "ACCEPTANCE.json", acceptance_record)
        make_manifest(bundle)
        verified = verify_bundle(bundle, source, require_domain_gates=False)
        write_json(bundle / "VERIFICATION.json", verified)
        if profile == "full" and any(g["status"] != "passed" for g in current_gates):
            write_json(bundle / "FULL_INCOMPLETE.json", {"gates": [g for g in current_gates if g["status"] != "passed"],
                       "source_checks": verified["status"], "full_acceptance": False})
            make_manifest(bundle)
            raise RuntimeError(f"Full acceptance incomplete. All source and tamper checks executed. Evidence preserved at {bundle}")
        return {"bundle": str(bundle), **verified}
    except BaseException as error:
        write_json(bundle / "FAILURE.json", {"error": str(error), "type": type(error).__name__, "at": now()})
        if (bundle / "MANIFEST.json").exists():
            make_manifest(bundle)
        raise


def dispatch(args) -> dict:
    if args.command == "acceptance":
        return acceptance(args.run_id, args.profile)
    if args.command in {"bench", "stress"}:
        from .quality import engineering_campaign
        return engineering_campaign(args.command)
    if args.command == "docs":
        from .quality import check_documentation
        return check_documentation()
    if args.command == "release":
        from .publication import package_release
        return package_release(args.evidence)
    raise ValueError("Unsupported campaign command")
