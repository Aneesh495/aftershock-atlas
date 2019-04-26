from datetime import date, timedelta

from aftershock.state_surveillance import matched_beds, pcr_week, vaccination_reports, vaccination_week

CATEGORIES = ["Positive", "Negative", "Inconclusive"]


def test_paired_facility_ratio_uses_bed_day_denominators_and_requires_full_window():
    start = date(2020, 4, 6)
    source = [
        (start + timedelta(days=i), {"icu_numerator": "5", "icu_denominator": "10", "icu_coverage": "4"})
        for i in range(7)
    ]
    source[-1][1]["icu_denominator"] = "25"
    assert matched_beds(source, "icu")["weekly_percent"] == 100 * 35 / 85
    source[-1][1]["icu_coverage"] = ""
    incomplete = matched_beds(source, "icu")
    assert incomplete["paired_days"] == 6
    assert incomplete["weekly_percent"] is None
    assert incomplete["occupied_bed_days"] == 30


def test_pcr_zero_is_reported_and_negative_correction_withholds_ratio():
    start = date(2020, 4, 6)
    source = [
        (start + timedelta(days=i), {"overall_outcome": outcome, "new_results_reported": value,
                                     "total_results_reported": ""})
        for i in range(7)
        for outcome, value in zip(CATEGORIES, ("0", "10", "2"), strict=True)
    ]
    assert pcr_week(source, CATEGORIES)["weekly_positivity_percent"] == 0
    assert pcr_week(source, CATEGORIES)["determinate_results"] == 70
    source[0][1]["new_results_reported"] = "-3"
    result = pcr_week(source, CATEGORIES)
    assert result["positive"]["reported_total"] == -3
    assert result["weekly_positivity_percent"] is None
    assert result["negative_result_corrections"] == 1
    source[0][1]["new_results_reported"] = ""
    assert pcr_week(source, CATEGORIES)["positive"]["days"] == 6


def test_cumulative_vaccination_retains_signed_report_update_and_public_cap():
    def report(count):
        return {"series_complete_yes": count, "series_complete_pop_pct": "95", "administered": "120"}

    start = date(2021, 9, 6)
    grouped = vaccination_reports([
        ("AZ", start, report("100")),
        ("AZ", start + timedelta(days=9), report("96")),
    ], [95, 99.9])
    gap_week = vaccination_week(grouped["AZ", start + timedelta(days=7)])
    assert gap_week["negative_completion_updates"] == 1
    snapshot = gap_week["latest_report"]
    assert snapshot["signed_primary_series_update"] == -4
    assert snapshot["days_since_previous_report"] == 9
    assert snapshot["matches_documented_cap"] is True
