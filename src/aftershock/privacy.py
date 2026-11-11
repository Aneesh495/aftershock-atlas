"""One disclosure boundary shared by cache generation, API and exports."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Disclosure:
    minimum_cell: int = 20
    maximum_relative_se: float = .3

    def reason(self, row: dict) -> str | None:
        if row.get("suppressed") or "suppressed" in row.get("flags", ""):
            return row.get("suppression_reason", "provider suppression")
        if row.get("group", "total") == "total":
            return None
        # Already published aggregates can be relayed without inventing their sample size.
        if row.get("release_basis") == "upstream_public_aggregate":
            return None
        n = row.get("sample_n")
        if n is None or n < self.minimum_cell:
            return "unknown or small sample cell"
        value, se = row.get("value"), row.get("se")
        if value and se is not None and abs(se / value) > self.maximum_relative_se:
            return "unstable estimate"
        return None

    def apply(self, row: dict) -> dict:
        reason = self.reason(row)
        result = {k: v for k, v in row.items() if k not in {"person_id", "sample_n", "raw_weight", "respondent"}}
        if reason:
            for key in ("value", "lower", "upper", "denominator", "se", "count", "weight_sum"):
                if key in result:
                    result[key] = None
            result["suppressed"] = True
            result["suppression_reason"] = reason
        return result

    def table(self, rows: list[dict], exhaustive: bool = False) -> list[dict]:
        safe = [self.apply(row) for row in rows]
        if exhaustive:
            hidden = [i for i, row in enumerate(safe) if row.get("suppressed")]
            visible = [i for i, row in enumerate(safe) if not row.get("suppressed") and row.get("value") is not None]
            if len(hidden) == 1 and visible:
                candidate = min(visible, key=lambda i: abs(safe[i]["value"]))
                safe[candidate] = self.apply({**safe[candidate], "suppressed": True})
                safe[candidate]["suppression_reason"] = "complementary suppression"
        return safe
