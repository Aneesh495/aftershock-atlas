# Work and education measurement

The [registered protocol](MEASUREMENT_PLAN_V4.md) adds separate measurement tables for annual hours, PISA scores and adult remote-instruction reports. Produce the tables with `make measurement-data measurement studies atlas` after building the core panel and fitting the core models. The report below describes the pinned input vintage.

| Measure | Reconstructed rows | Main finding |
| --- | ---: | --- |
| OECD annual actual hours per employed person | 90 comparisons across 45 countries | Hours fell in all 45 matched series in 2020. Median change was -4.26%. |
| OECD PISA education-system assessments | 243 system-subject rows | Median 2018 to 2022 changes across eligible systems were -8.36 in mathematics, -6.91 in reading and -0.62 in science. |
| Census Household Pulse adult proxy reports | 110 aggregates, including 23 suppressed | 71.94% reported classes moving online, with a 95% design interval of 70.49% to 73.39%. There were 20,122 complete adult responses to this item. |

## Work hours

The annual OECD series includes employees and self-employed workers. The 2019 anchor must be positive and every year through the endpoint must be present under the same definition. In the 2022 comparison, 43 series met this rule. The median was 1.30% below 2019, 33 series fell, nine increased and one stayed at its baseline. GDP per person moved in the opposite direction from hours in 30 of the 43 matched series. These are descriptive finite-panel changes, without published sampling errors.

Methods vary by country. A year-to-year change uses only observations from the same country series. An index comparison preserves the distinction between output per resident and annual hours per worker. The OECD aggregate is excluded. Weekly hours, industry breakdowns and individual exposure remain unresolved after the attempted ILO metadata routes returned empty responses. [OECD source and measurement guidance](https://www.oecd.org/en/data/indicators/hours-worked.html)

## Learning

The three pinned sheets cover 81 education systems. Published 2018 to 2022 changes were usable for 62 mathematics systems and 61 systems in each other subject after excluding sampling or linkage cautions. Their source trend standard errors incorporate the link error described by OECD. After within-subject Benjamini-Hochberg adjustment, mathematics had 29 declines and seven increases at 5%, reading had 31 declines and six increases, and science had 18 declines and 13 increases. The results include a sensitivity that retains the cautioned systems descriptively. Changes between 2015 and 2018 use mean differences over a three-year span and omit change intervals.

The eligible population includes enrolled students of the target age. Changes in assessment participation, school enrollment, sampling and scale linkage affect interpretation. The protocol supplies separate identities for partial education systems, and withholds country navigation links for ambiguous matches. These descriptive changes cannot isolate the effect of closure length or remote instruction. [OECD workbook](https://stat.link/wh9d4z) · [Scale-linking methodology](https://www.oecd.org/en/publications/2023/12/pisa-2022-results-volume-i_76772a36/full-report/comparing-mathematics-reading-and-science-performance-across-pisa-assessments_1c417d6f.html)

## Instruction

Adult weights target reports from adults with children enrolled in public or private K-12 in February 2020. The questionnaire permits multiple teaching arrangements. It reports live contact through phone or video over seven days and top-codes the associated hours. Mean reported live contact was 4.05 hours, with a 95% design interval of 3.86 to 4.25. The 19,491 complete adult reports for that item had an estimated 28.61% at zero hours. Weighted missing-item bounds describe uncertainty among eligible respondents. The provider's 3.8% weighted unit response rate is contextual. The design intervals do not adjust for unit nonresponse.

The repository stores derived aggregate cells and the archive identity. The analysis and its independent verifier stream the public-use roster and 80 replicate weights locally. Suppression clears the estimates, intervals and denominators for inadequate, unstable or rare response cells. [Census 2020 survey files and codebooks](https://www.census.gov/data/datasets/time-series/demo/hhp/2020.html)

## Audit

The verifier reads the underlying workbook XML directly, rebuilds the PISA multiplicity families, and checks published score cells and uncertainty against selected source coordinates. It reconstructs the hours episodes against the frozen OECD CSV and independently parsed World Bank GDP. A separate weighted matrix computation audits every non-suppressed survey estimate and tests suppressed fields. The campaign records rehashed changes to the hours definition, hours-GDP join, assessment standard error and survey denominator.

S08 and S09 now have bounded analyses. The limited occupational scope of S04 and later-wave survey coverage in S10 remain open. Full acceptance requires the outstanding measurement, chronology, survey, calibration and release checks.
