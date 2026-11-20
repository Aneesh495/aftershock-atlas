"""Restore fixed public UK and Connecticut releases for portable replay."""
from __future__ import annotations

import shutil
from pathlib import Path
from zipfile import ZipFile

from .acquire import Source, acquire_one
from .io import ROOT, atomic_path, contained, digest, read_json
from .resources import usage
from .uk_vintages import RAW, pinned_items


def chronology_pins() -> list[dict]:
    return [*pinned_items(), *read_json(ROOT / "configs/ct-crosswalk-inputs.json").values()]


def restore_chronology(raw: Path = RAW) -> dict:
    pins = chronology_pins()
    absent = []
    for pin in pins:
        path = contained(raw, pin["path"])
        if not path.exists():
            absent.append(pin)
        elif path.stat().st_size != pin["bytes"] or digest(path) != pin["sha256"]:
            raise ValueError(f"Chronology input checksum differs: {pin['id']}")
    if not absent:
        return {"sources": len(pins), "restored": 0}
    frozen = read_json(ROOT / "configs/CHRONOLOGY_SNAPSHOT.json")
    spec = Source("chronology_snapshot", frozen["url"], "zip", 30_000_000,
                  "ONS Open Government Licence and Census US government public aggregates",
                  frozen["url"], "Frozen public archive bytes", "No survey records")
    receipt = acquire_one(spec, raw)
    if receipt["sha256"] != frozen["sha256"] or receipt["bytes"] != frozen["bytes"]:
        raise ValueError("Chronology snapshot checksum differs")
    expected = {pin["path"]: pin for pin in pins}
    usage(sum(pin["bytes"] for pin in absent) + 3_000_000)
    with ZipFile(contained(raw, receipt["path"])) as archive:
        members = {member.filename: member for member in archive.infolist()}
        if len(members) != len(archive.infolist()) or set(members) != set(expected) or any(
            member.file_size != expected[name]["bytes"] or not expected[name]["redistribute"]
            for name, member in members.items()
        ):
            raise ValueError("Chronology snapshot member set or expanded size changed")
        for record in absent:
            path = contained(raw, record["path"])
            with atomic_path(path) as target, archive.open(record["path"]) as input_file:
                with target.open("wb") as output:
                    shutil.copyfileobj(input_file, output, length=1 << 20)
                if digest(target) != record["sha256"]:
                    raise ValueError(f"Chronology snapshot member checksum differs: {record['id']}")
    return {"sources": len(pins), "restored": len(absent)}
