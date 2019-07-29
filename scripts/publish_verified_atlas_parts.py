#!/usr/bin/env python3
"""Merge GitHub's verified aggregate extension partitions into the tracked atlas."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

REPO = "Aneesh495/aftershock-atlas"
ROOT = Path(__file__).resolve().parents[1]
PARTS = ("ct-crosswalk", "uk-vintages", "social-context", "uk-forecast")
EXTENDED = ("territory-audit", "mortality-calibration")


def api(route: str) -> bytes:
    return subprocess.check_output(["gh", "api", f"repos/{REPO}/{route}"], timeout=100)


def identity(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive_content(meta: dict, limit: int) -> ZipFile:
    if meta["expired"] or not 0 < meta["size_in_bytes"] <= limit:
        raise ValueError("Runner artifact is unavailable or above its byte bound")
    data = api(f'actions/artifacts/{meta["id"]}/zip')
    if len(data) != meta["size_in_bytes"] or "sha256:" + identity(data) != meta["digest"]:
        raise ValueError("Runner artifact container checksum differs")
    archive = ZipFile(io.BytesIO(data))
    inventory = archive.infolist()
    if len(inventory) != len(set(archive.namelist())) or len(inventory) > 380 or (
        sum(item.file_size for item in inventory) > 195_000_000
    ):
        archive.close()
        raise ValueError("Runner artifact exceeds its expanded inventory bound")
    return archive


def raw_json(z: ZipFile, name: str, limit: int = 3_000_000) -> tuple[dict, bytes]:
    if not 0 < z.getinfo(name).file_size <= limit:
        raise ValueError(f"Runner artifact member exceeds its read bound: {name}")
    payload = z.read(name)
    return json.loads(payload), payload


def artifact_sources() -> dict[str, dict]:
    def config(name: str):
        return json.loads((ROOT / "configs" / name).read_bytes())
    geography = config("ct-crosswalk-inputs.json")
    context = config("social-context-inputs.json")
    editions = config("uk-vintages-inputs.json")
    versions = [editions["catalogue"], *(row[part] for row in editions["editions"] for part in ("workbook", "bulletin"))]
    return {entry["id"]: {**{k: v for k, v in entry.items() if k not in {"headers", "path"}}, "status": "acquired"}
            for entry in (*geography.values(), *context.values(), *versions)}


def dumps(payload) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def publish(run: int, expected: str, check_only: bool) -> dict:
    run_meta = json.loads(api(f"actions/runs/{run}"))
    if run_meta["head_sha"] != expected or run_meta["status"] != "completed":
        raise ValueError("Exact expected research run is incomplete or at a different source")
    if run_meta["name"] != "Frozen research campaign":
        raise ValueError("Artifacts must come from the research campaign workflow")
    metadata = json.loads(api(f"actions/runs/{run}/artifacts?per_page=100"))["artifacts"]
    assets = {a["name"]: a for a in metadata}
    reports = assets["research-results-and-manifests"]
    published = assets["verified-chronology-atlas-parts"]
    with archive_content(reports, 21_000_000) as evidence:
        matches = [name for name in evidence.namelist() if re.fullmatch(r"[a-zA-Z0-9_-]+/VERIFICATION.json", name)]
        if len(matches) != 1:
            raise ValueError("Research verification receipt is missing or ambiguous")
        receipt, _ = raw_json(evidence, matches[0])
        prefix = matches[0].removesuffix("VERIFICATION.json")
        manifest, bundle_manifest_payload = raw_json(evidence, prefix + "MANIFEST.json")
        controls, controls_payload = raw_json(evidence, prefix + "negative-controls.json")
        if identity(controls_payload) != manifest["files"]["negative-controls.json"]["sha256"]:
            raise ValueError("Tamper receipt differs from the frozen evidence manifest")
        if not (receipt["source"] == controls["source"] == expected and receipt["status"] in {
            "passed", "source_checks_passed_full_incomplete"
        }) or len(controls["controls"]) != controls["rejected"] or controls["rejected"] < 39 or (
            any(check["exit"] != 1 for check in controls["controls"])
        ):
            raise ValueError("Research replay or controls did not attest the selected scientific results")
        if not {"geography", "uk_releases", "uk_forecast", "social_context"} <= receipt.keys():
            raise ValueError("Required independent extension verifications are missing")
        count = len(evidence.read(prefix + "COMMANDS.jsonl").splitlines())
        incomplete = []
        if prefix + "FULL_INCOMPLETE.json" in evidence.namelist():
            incomplete, _ = raw_json(evidence, prefix + "FULL_INCOMPLETE.json")
            incomplete = incomplete["gates"]
    directory = ROOT / "client/public/data"
    old_index = json.loads((directory / "index.json").read_bytes())
    parts = PARTS + EXTENDED if {"territory_audit", "mortality_calibration"} <= receipt.keys() else PARTS
    checks = 42 if parts != PARTS else 39
    if controls["rejected"] < checks:
        raise ValueError("Research control inventory does not support the public partition set")
    files = {}
    with archive_content(published, 2_000_000) as atlas:
        if {f"{name}.json" for name in parts} | {"index.json"} != set(atlas.namelist()):
            raise ValueError("Runner public partition names differ from the declared subset")
        new_index, _ = raw_json(atlas, "index.json")
        if new_index["source_commit"] != expected or new_index["panel_sha256"] != old_index["panel_sha256"]:
            raise ValueError("The extension snapshot changes the shared panel or scientific source")
        for part in parts:
            name = part + ".json"
            data, payload = raw_json(atlas, name)
            if data["source"] != expected or identity(payload) != new_index["files"][name] or (
                identity(payload) != manifest["files"][name]["sha256"]
            ):
                raise ValueError(f"Published partition detached from research data: {name}")
            files[name] = payload
    source_library = {s["id"]: s for s in json.loads((directory / "sources.json").read_bytes())}
    source_library.update(artifact_sources())
    files["sources.json"] = dumps(list(source_library.values()))
    receipt_data = {
        "source": expected, "runner": f"https://github.com/{REPO}/actions/runs/{run}",
        "artifact_id": reports["id"], "artifact_digest": reports["digest"],
        "public_artifact_id": published["id"], "public_artifact_digest": published["digest"],
        "manifest_sha256": identity(bundle_manifest_payload), "command_count": count,
        "negative_controls": controls, "verification": receipt, "remaining_gates": incomplete,
        "partitions": {name: identity(files[name]) for name in files if name != "sources.json"},
    }
    if not check_only:
        for name, payload in files.items():
            (directory / name).write_bytes(payload)
            old_index["files"][name] = identity(payload)
        old_index["published_extensions"] = {
            "source": expected, "campaign": receipt_data["runner"], "partitions": receipt_data["partitions"],
        }
        old_index["built_at"] = datetime.now(timezone.utc).isoformat()
        (directory / "index.json").write_bytes(dumps(old_index))
        (ROOT / "docs/CHRONOLOGY_AND_CALIBRATION_RECEIPT.json").write_bytes(dumps(receipt_data))
    return {k: receipt_data[k] for k in ("source", "runner", "command_count", "partitions", "remaining_gates")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=int)
    parser.add_argument("expected_source")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(publish(args.run, args.expected_source, args.check_only), indent=2))
