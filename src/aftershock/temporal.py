"""Bitemporal selection never replaces a missing historical vintage with final data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


def stamp(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Timestamp must carry timezone")
    return value


def as_of(rows: list[dict], cutoff: str, event_end: str | None = None) -> list[dict]:
    bound = stamp(cutoff)
    chosen: dict[tuple, dict] = {}
    versions: set[tuple] = set()
    for row in rows:
        available = stamp(row["available_at"])
        vintage = stamp(row["vintage"])
        if available < vintage:
            raise ValueError("Availability precedes the recorded acquisition vintage")
        if available > bound or (event_end and row["event_end"] > event_end):
            continue
        key = tuple(row[k] for k in ("region", "metric", "event_start", "event_end", "group"))
        identity = (*key, row["vintage"])
        if identity in versions:
            raise ValueError("Duplicate population within vintage")
        versions.add(identity)
        if key not in chosen or available > stamp(chosen[key]["available_at"]):
            chosen[key] = row
    return [chosen[k] for k in sorted(chosen)]


def revision_ledger(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        key = tuple(row[k] for k in ("region", "metric", "event_start", "group"))
        grouped.setdefault(key, []).append(row)
    out = []
    for key, versions in sorted(grouped.items()):
        ordered = sorted(versions, key=lambda r: stamp(r["available_at"]))
        for prior, current in zip(ordered, ordered[1:]):
            before, after = prior["value"], current["value"]
            out.append({"region": key[0], "metric": key[1], "event_start": key[2], "group": key[3],
                        "prior_vintage": prior["vintage"], "next_vintage": current["vintage"],
                        "delta": None if before is None or after is None else after - before,
                        "became_missing": before is not None and after is None})
    return out


@dataclass(frozen=True)
class Phase:
    region: str
    outcome: str
    label: str
    start: date
    end: date
    basis: str


def validate_phases(phases: list[Phase]) -> None:
    seen: dict[tuple, list[Phase]] = {}
    for phase in phases:
        if phase.start > phase.end or not phase.basis:
            raise ValueError("Invalid phase or missing phase justification")
        seen.setdefault((phase.region, phase.outcome), []).append(phase)
    for group in seen.values():
        ordered = sorted(group, key=lambda p: p.start)
        if any(a.end >= b.start for a, b in zip(ordered, ordered[1:])):
            raise ValueError("Overlapping outcome phases")
