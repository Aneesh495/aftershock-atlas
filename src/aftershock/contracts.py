"""Measurement, availability, and public disclosure contracts."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum


class Kind(StrEnum):
    OBSERVED = "observed"
    SURVEY = "survey_estimate"
    MODELED = "modeled_estimate"
    IMPUTED = "imputed"
    POLICY = "policy_design"
    GENETIC = "genomic_association"
    LINEAGE = "lineage_submission"


@dataclass(frozen=True)
class Metric:
    id: str
    title: str
    family: str
    unit: str
    frequency: str
    kind: Kind
    definition: str
    minimum: float | None = None
    maximum: float | None = None
    signed: bool = False
    denominator: str | None = None

    def validate(self, value: float | None) -> None:
        if value is None:
            return
        if not math.isfinite(value):
            raise ValueError(f"Nonfinite {self.id}")
        if self.minimum is not None and value < self.minimum and not self.signed:
            raise ValueError(f"Below domain {self.id}: {value}")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"Above domain {self.id}: {value}")

    def public(self) -> dict:
        return asdict(self)


METRICS = {m.id: m for m in [
    Metric("covid_cases", "Reported COVID cases", "surveillance", "cases", "weekly", Kind.OBSERVED,
           "New cases by date reported to WHO; detection and reporting vary", signed=True),
    Metric("covid_deaths", "Reported COVID deaths", "surveillance", "deaths", "weekly", Kind.OBSERVED,
           "New deaths by date reported to WHO; corrections retained", signed=True),
    Metric("population", "Population", "denominators", "people", "annual", Kind.MODELED,
           "World Bank population estimates; annual vintage", minimum=0),
    Metric("employment", "Employment to population", "work", "percent age 15+", "annual", Kind.MODELED,
           "ILO modeled employment ratio, total age 15+; estimates can revise", 0, 100),
    Metric("gdp", "Real GDP per person", "economy", "constant 2015 USD/person", "annual", Kind.OBSERVED,
           "World Bank NY.GDP.PCAP.KD; national accounts in constant 2015 US dollars", minimum=0),
    Metric("school", "Secondary school enrollment", "education", "gross percent", "annual", Kind.OBSERVED,
           "Gross secondary enrollment includes pupils outside the official age range; may exceed 100", 0),
    Metric("immunization", "Routine DTP immunization", "health_services", "percent ages 12-23 months",
           "annual", Kind.MODELED, "WHO/UNICEF DPT coverage estimates, not direct service-use counts", 0, 100),
    Metric("mortality", "Crude all-cause mortality", "mortality", "deaths/1000 people/year", "annual",
           Kind.MODELED, "WDI demographic estimates, not daily registered deaths or excess mortality", 0),
    Metric("life_expectancy", "Life expectancy at birth", "longevity", "years", "annual", Kind.MODELED,
           "Period life expectancy estimate; not an individual forecast", 0, 120),
    Metric("stringency", "Policy stringency", "policy", "index 0-100", "daily", Kind.POLICY,
           "OxCGRT national total weighted policy index; not enforcement or adherence", 0, 100),
    Metric("school_policy", "School closure policy", "policy", "ordinal 0-3", "daily", Kind.POLICY,
           "OxCGRT C1M majority-population school closure policy", 0, 3),
    Metric("work_policy", "Workplace closure policy", "policy", "ordinal 0-3", "daily", Kind.POLICY,
           "OxCGRT C2M majority-population workplace closure policy", 0, 3),
    Metric("allcause_weekly", "Registered all-cause deaths", "mortality", "deaths", "weekly", Kind.OBSERVED,
           "CDC state of occurrence, event week; pre-2020 final and 2020-2023 provisional", 0),
    Metric("anxiety", "Anxiety or depression symptoms", "mental_health", "weighted percent adults", "survey_wave",
           Kind.SURVEY, "Household Pulse published weighted PHQ-2/GAD-2 symptom estimate, past 7 days", 0, 100),
]}


@dataclass(frozen=True)
class Observation:
    region: str
    metric: str
    event_start: str
    event_end: str
    value: float | None
    available_at: str
    vintage: str
    source: str
    source_hash: str
    kind: str
    unit: str
    frequency: str
    group: str = "total"
    lower: float | None = None
    upper: float | None = None
    denominator: float | None = None
    flags: str = ""

    def validate(self) -> None:
        m = METRICS[self.metric]
        m.validate(self.value)
        if self.unit != m.unit or self.kind != m.kind:
            raise ValueError("Measurement definition mismatch")
        if date.fromisoformat(self.event_start) > date.fromisoformat(self.event_end):
            raise ValueError("Reversed event interval")
        if datetime.fromisoformat(self.available_at).tzinfo is None:
            raise ValueError("Availability needs timezone")
        if len(self.source_hash) != 64 or not self.region:
            raise ValueError("Missing source or region identity")
        if self.lower is not None and self.upper is not None:
            if not self.lower <= self.value <= self.upper:
                raise ValueError("Invalid interval")
        if self.denominator is not None and self.denominator <= 0:
            raise ValueError("Nonpositive denominator")

    def record(self) -> dict:
        self.validate()
        return asdict(self)
