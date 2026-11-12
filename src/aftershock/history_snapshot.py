"""Bounded restoration and deterministic preparation of public archive partitions."""
from __future__ import annotations

import shutil
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from .acquire import Source, acquire_one
from .io import ROOT, atomic_path, contained, digest, read_json, write_json
from .resources import usage


def prepare_history_snapshot() -> dict:
    pins = read_json(ROOT / "configs/history-inputs.json")
    usage(sum(record["bytes"] for record in pins.values()) + 5_000_000)
    path = ROOT / "releases/aftershock-history-inputs.zip"
    path.parent.mkdir(exist_ok=True)
    members = {record["path"]: ROOT / "data/history/raw" / record["path"] for record in pins.values()}
    members["HISTORY_INPUTS.json"] = ROOT / "configs/history-inputs.json"
    members["DATA_RIGHTS.md"] = ROOT / "docs/DATA_RIGHTS.md"
    with atomic_path(path) as temporary:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
            for name in sorted(members):
                origin = members[name]
                if name not in {"HISTORY_INPUTS.json", "DATA_RIGHTS.md"}:
                    record = next(r for r in pins.values() if r["path"] == name)
                    if digest(origin) != record["sha256"]:
                        raise ValueError("Historical bytes changed before snapshot preparation")
                member = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                member.create_system = 3
                member.external_attr = 0o100444 << 16
                member.compress_type = ZIP_DEFLATED
                with origin.open("rb") as source, archive.open(member, "w") as target:
                    shutil.copyfileobj(source, target, 1 << 20)
        if temporary.stat().st_size > 80_000_000:
            raise ValueError("Prepared history snapshot exceeds compressed bound")
    result = {"url": "https://github.com/Aneesh495/aftershock-atlas/releases/download/v0.2.0-preview/aftershock-history-inputs.zip",
        "sha256": digest(path), "bytes": path.stat().st_size, "sources": len(pins),
        "expanded_bytes": sum(r["bytes"] for r in pins.values()),
        "source_manifest_sha256": digest(ROOT / "configs/history-inputs.json"), "raw_survey_included": False}
    write_json(ROOT / "configs/HISTORY_SNAPSHOT.json", result)
    return result


def restore_history(raw: Path, local_archive: Path | None = None) -> dict:
    snapshot = read_json(ROOT / "configs/HISTORY_SNAPSHOT.json")
    pins = read_json(ROOT / "configs/history-inputs.json")
    if digest(ROOT / "configs/history-inputs.json") != snapshot["source_manifest_sha256"]:
        raise ValueError("Historical snapshot manifest differs from frozen inputs")
    if local_archive is None:
        source = Source("history_snapshot", snapshot["url"], "zip", 80_000_000,
            "World Bank CC BY 4.0 with additional terms; see frozen source manifest", snapshot["url"],
            "immutable archive-edition snapshot", "Public aggregate archive bytes only; no respondent records")
        received = acquire_one(source, raw)
        path = raw / received["path"]
    else:
        path = local_archive
    if digest(path) != snapshot["sha256"] or path.stat().st_size != snapshot["bytes"]:
        raise ValueError("Historical restoration archive identity mismatch")
    usage(snapshot["expanded_bytes"] + 10_000_000)
    expected = {r["path"]: r for r in pins.values()}
    with ZipFile(path) as archive:
        members = archive.infolist()
        if len({m.filename for m in members}) != len(members) or set(archive.namelist()) != set(expected) | {"HISTORY_INPUTS.json", "DATA_RIGHTS.md"}:
            raise ValueError("Unexpected historical snapshot member set")
        if sum(m.file_size for m in members) > snapshot["expanded_bytes"] + 2_000_000:
            raise ValueError("Historical snapshot expansion exceeds budget")
        import hashlib
        if hashlib.sha256(archive.read("HISTORY_INPUTS.json")).hexdigest() != snapshot["source_manifest_sha256"]:
            raise ValueError("Historical snapshot source metadata mismatch")
        for name, record in expected.items():
            member = archive.getinfo(name)
            if member.file_size != record["bytes"] or ((member.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("Invalid historical snapshot member type or size")
            destination = contained(raw, name)
            with atomic_path(destination) as temporary:
                with archive.open(member) as source, temporary.open("wb") as output:
                    shutil.copyfileobj(source, output, 1 << 20)
                if digest(temporary) != record["sha256"]:
                    raise ValueError("Historical snapshot member checksum mismatch")
            write_json(raw / record["id"] / "latest.json", record)
    write_json(raw / "index.json", pins)
    return {"sources_restored": len(pins), "archive_sha256": snapshot["sha256"], "source": "local_prepared_archive" if local_archive else "release_download"}
