"""Aggregate host-variant harmonization, separate from viral and geographic evidence."""
from __future__ import annotations

import csv
import gzip
import math
from dataclasses import dataclass
from pathlib import Path

from scipy.special import log_ndtr

from .io import ROOT, read_json, write_json
from .statistics import bh_adjust

COMPLEMENT = str.maketrans("ACGT", "TGCA")


@dataclass(frozen=True)
class Association:
    chromosome: str
    position: int
    reference: str
    effect: str
    beta: float
    se: float
    p: float
    frequency: float | None
    cases: int
    controls: int
    build: str = "GRCh38"

    def validate(self) -> None:
        if self.build not in {"GRCh38", "GRCh37"} or self.position < 1:
            raise ValueError("Unknown reference build or coordinate")
        if not math.isfinite(self.beta) or not math.isfinite(self.se) or self.se <= 0 or not 0 <= self.p <= 1:
            raise ValueError("Invalid association statistic")
        if self.reference == self.effect or not self.reference or not self.effect:
            raise ValueError("Invalid alleles")
        if self.frequency is not None and not 0 <= self.frequency <= 1:
            raise ValueError("Invalid allele frequency")
        if self.cases <= 0 or self.controls <= 0:
            raise ValueError("Positive aggregate sample counts required")

    @property
    def key(self) -> tuple:
        return self.build, self.chromosome, self.position


def align(reference: Association, candidate: Association) -> tuple[float | None, str]:
    reference.validate()
    candidate.validate()
    if reference.key != candidate.key:
        raise ValueError("Reference build or position mismatch; liftover is not implicit")
    a, b = (reference.reference, reference.effect), (candidate.reference, candidate.effect)
    ambiguous = set(a) in ({"A", "T"}, {"C", "G"})
    if ambiguous and (candidate.frequency is None or .4 <= candidate.frequency <= .6):
        return None, "ambiguous_strand"
    if b == a:
        return candidate.beta, "exact"
    if b[::-1] == a:
        return -candidate.beta, "swapped_effect"
    if all(len(allele) == 1 and allele in "ACGT" for allele in b):
        complement = tuple(allele.translate(COMPLEMENT) for allele in b)
        if complement == a and not ambiguous:
            return candidate.beta, "strand_complement"
        if complement[::-1] == a and not ambiguous:
            return -candidate.beta, "strand_complement_swapped"
    return None, "allele_mismatch"


def read_associations(path: Path, cap: int = 15000) -> list[Association]:
    if path.stat().st_size > 5_000_000:
        raise ValueError("Summary-statistic input exceeds budget")
    rows, identities = [], set()
    with gzip.open(path, "rt") as f:
        for i, row in enumerate(csv.DictReader(f, delimiter="\t")):
            if i >= cap:
                raise ValueError("Unexpected summary-statistic expansion")
            frequency = row["all_meta_AF"]
            association = Association(row["#CHR"], int(row["POS"]), row["REF"], row["ALT"],
                                      float(row["all_inv_var_meta_beta"]), float(row["all_inv_var_meta_sebeta"]),
                                      float(row["all_inv_var_meta_p"]), None if frequency == "NA" else float(frequency),
                                      int(float(row["all_inv_var_meta_cases"])), int(float(row["all_inv_var_meta_controls"])))
            association.validate()
            key = (*association.key, association.reference, association.effect)
            if key in identities:
                raise ValueError("Duplicate aggregate association")
            identities.add(key)
            rows.append(association)
    if len(rows) < 100:
        raise ValueError("Empty or implausibly small aggregate analysis")
    return rows


def host_genetics() -> dict:
    raw = ROOT / "data/raw"
    index = read_json(raw / "index.json")
    a, b = [read_associations(raw / index[k]["path"]) for k in ("hgi_a2", "hgi_b2")]
    right = {(*r.key, r.reference, r.effect): r for r in b}
    aligned, exclusions, mismatches = [], {}, 0
    for r in a:
        key = (*r.key, r.reference, r.effect)
        if key not in right:
            continue
        other = right[key]
        beta, reason = align(r, other)
        if beta is None:
            exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        log_p = float(math.log(2) + log_ndtr(-abs(r.beta / r.se)))
        if r.p > 0 and abs(math.log(r.p) - log_p) > .1:
            mismatches += 1
        aligned.append({"chromosome": r.chromosome, "position": r.position, "reference": r.reference,
                        "effect_allele": r.effect, "build": r.build, "a2_beta": r.beta, "a2_se": r.se, "a2_p": r.p,
                        "b2_beta_aligned": beta, "b2_se": other.se, "b2_p": other.p,
                        "same_direction": r.beta * beta > 0, "alignment": reason,
                        "a2_odds_ratio": math.exp(r.beta), "a2_lower": math.exp(r.beta - 1.96 * r.se),
                        "a2_upper": math.exp(r.beta + 1.96 * r.se), "a2_cases": r.cases, "a2_controls": r.controls})
    adjusted = bh_adjust([r["a2_p"] for r in aligned])
    for row, q in zip(aligned, adjusted):
        row["selected_set_bh_q"] = q
    # One representative per 1 Mb bin is a display compression, never an LD claim.
    display, bins = [], set()
    for row in sorted(aligned, key=lambda r: r["a2_p"]):
        bin_id = (row["chromosome"], row["position"] // 1_000_000)
        if bin_id not in bins and len(display) < 20:
            display.append(row)
            bins.add(bin_id)
    result = {"analysis": "host_genetics_aggregate_methods", "source": "HGI release 7; April 2022",
              "source_hashes": {k: index[k]["sha256"] for k in ("hgi_a2", "hgi_b2")},
              "input_variants": {"A2": len(a), "B2": len(b)}, "aligned_variants": len(aligned),
              "direction_concordant": sum(r["same_direction"] for r in aligned), "excluded": exclusions,
              "rounded_p_discrepancies_log_tolerance_0_1": mismatches,
              "genome_wide_threshold": 5e-8, "a2_below_threshold": sum(r.p < 5e-8 for r in a),
              "representatives": display, "display_bin_bp": 1_000_000,
              "independent_replication": False, "ld_independence_established": False,
              "sample_overlap": "A2 severe cases can be contained in B2 hospitalized cases; controls and contributing cohorts overlap",
              "multiplicity": "BH applies only to the selected 10000 variants; ascertainment prevents genome-wide FDR interpretation",
              "case_definitions": {"A2": "Very severe respiratory confirmed COVID versus population",
                                   "B2": "Hospitalized COVID versus population"},
              "limitations": ["Selected-variant release, not a genome-wide replication", "No LD reference or conditional association analysis",
                              "No individual ancestry inference", "No genetic explanation of national or ethnic group trajectories",
                              "Odds ratios are aggregate associations, not absolute personal risks"],
              "terms": "https://www.covid19hg.org/about/"}
    write_json(ROOT / "data/results/genetics.json", result)
    # Local restricted-to-purpose replay table is excluded from public atlas and source control.
    write_json(ROOT / "data/results/genetic-alignment.json", aligned)
    return result
