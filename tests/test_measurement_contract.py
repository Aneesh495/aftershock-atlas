import math

from aftershock.io import ROOT, read_json
from aftershock.remote_instruction import respondent_values
from aftershock.work_hours import contrast_rows


def test_remote_instruction_treats_fractional_hours_and_zero_as_responses():
    config = read_json(ROOT / "configs/measurement-v4.json")["census"]
    raw = {key: "-99" for key in config["items"]}
    raw.update(TEACH1="-88", TEACH2="1", TSCHLHRS="0.5", TTCH_HRS="0")
    result = respondent_values(raw, config)
    assert math.isnan(result[0])
    assert result[1:] == [1, 0, 0, 0, .5, 0, 0, 0, 1, 0]


def test_hours_comparison_withholds_breaks_and_gap_without_withholding_gdp():
    config = read_json(ROOT / "configs/measurement-v4.json")["hours"]
    values = {"AUS": {
        2019: {"value": 1500, "status": "A"},
        2020: {"value": 1400, "status": "A"},
        2021: {"value": 1600, "status": "B"},
        2022: {"value": 1650, "status": "A"},
    }}
    gdp = {("AUS", 2019): 10, ("AUS", 2020): 9, ("AUS", 2022): 12}
    a, b = contrast_rows(values, config, gdp, "h")
    assert a["change_hours"] == -100 and a["gdp_match"]
    assert b["hours_index"] is None and b["gdp_per_person_index"] == 120 and not b["gdp_match"]
    assert b["comparison_exclusions"] == ["status excludes comparison: B"]
    del values["AUS"][2021]
    assert contrast_rows(values, config, gdp, "h")[1]["comparison_exclusions"] == ["incomplete annual window"]
