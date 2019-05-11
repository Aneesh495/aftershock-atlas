# State surveillance and the Pulse survey recall change

The scientific executable is `8808b6fb129899a7bb6445607c866570d8d4c903`. The aggregate artifacts come from the [registered protocol](SURVEILLANCE_PLAN_V5.md), [surveillance source receipts](../configs/surveillance-inputs.json) and [survey source receipts](../configs/survey-bridge-inputs.json). Two independent implementations agree on 29,376 state-week rows and 66 survey estimates. The two raw Census archives remain separate from the public atlas and evidence exports.

## Surveillance

| Scope across 50 states and DC | Frozen source rows | Possible state-weeks | With reports | With seven report dates |
| --- | ---: | ---: | ---: | ---: |
| HHS hospital and ICU | 77,730 | 11,526 | 11,144 | 11,034 |
| HHS diagnostic PCR | 225,525 | 11,373 | 10,838 | 10,751 |
| CDC vaccine primary series | 30,447 | 6,477 | 6,426 | 3,978 |

The hospital archive supports 10,074 complete confirmed adult admission totals and 10,052 confirmed adult ICU patient means. The provider supplies matched facility denominators for 9,969 weekly all-cause adult ICU ratios and 9,857 confirmed-or-suspected COVID ICU ratios. Facility reporting lags and nonresponse limit the totals. The confirmed admission coverage column has an ambiguous source description and is retained only in the raw capture. [HHS hospital aggregation notes](https://healthdata.gov/stories/s/COVID-19-Reported-Patient-Impact-and-Hospital-Capa/t9hg-szrf/).

The PCR archive supports 10,531 weekly positivity ratios. Five negative recorded results in five state-weeks withhold positivity under the prespecified rule. This denominator counts determinate reported PCR results. Dates and location assignments can depend on what reports are available. [HHS PCR metadata](https://healthdata.gov/d/j8mb-icvb).

Vaccination has 110 negative report-to-report updates in resident primary-series completions. Displayed weekly coverage uses the latest available report in that week. No weekly latest total-population percentage in this cohort matches a documented cap value. Administered doses separately follow administration jurisdiction, and gaps remain visible. [CDC vaccination series](https://data.cdc.gov/d/unsk-b7fc) and [definition notes](https://archive.cdc.gov/www_cdc_gov/coronavirus/2019-ncov/vaccines/reporting-vaccinations.html).

## Survey design

| Separate adult estimates | Week 33, seven-day recall | Week 34, fourteen-day recall |
| --- | ---: | ---: |
| Provider weighted household response | 6.3% | 6.1% |
| Anxiety symptoms | 24.53% [23.82, 25.25] | 26.98% [26.15, 27.81] |
| Depressive symptoms | 20.86% [20.15, 21.57] | 22.15% [21.36, 22.93] |
| Either symptom measure, all four items complete | 28.91% [28.08, 29.75] | 31.22% [30.32, 32.11] |
| Either, item-missing bounds | [21.92, 46.10]% | [26.02, 42.67]% |

The intervals reflect person-replicate sampling uncertainty. The item bounds use the weighted universe of eligible responders. Sensitivity to hypothetical unit nonresponse is tabulated separately. Thirty-two of 36 matched national and race/Hispanic-origin comparisons met the 0.15 percentage-point tolerance. Four combined-symptom comparisons differed by 0.15 to 0.34 points. The signed residuals, complete-case denominators, income groups, reference years, and dates are in the atlas and CSV. The survey instrument change prevents treating the two estimates as a linked change in distress. [Census methods](https://www.census.gov/programs-surveys/household-pulse-survey/technical-documentation/source-accuracy.2021.html), [instruments](https://www.census.gov/programs-surveys/household-pulse-survey/technical-documentation/questionnaires.2021.html) and [NCHS comparator](https://www.cdc.gov/nchs/covid19/pulse/mental-health.htm).

Run `make surveillance-data surveillance survey-bridge-data survey-bridge studies atlas` after the standard bootstrap and core analysis. `make acceptance PROFILE=full RUN_ID=<new-id>` executes both domain replays and records their evidence. The current scientific increment retains open gates for historical timing and territory, broader subgroup and labor evidence, pandemic uncertainty calibration and full integrated acceptance.
