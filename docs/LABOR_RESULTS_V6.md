# Occupational disruptions and actual sector hours

The [registered comparison](LABOR_PLAN_V6.md) uses three September CPS public-use snapshots and a quarterly Eurostat cube. The independently replayed executable is `2fc48f28d71f63ce225bff24f94cbff0714d5513`. The CPS September estimates use the Census basic files and separately released COVID supplement extracts. The 29 planned BLS workbook requests returned HTTP 403. The published BLS national headlines provide the three validation targets. [CPS exact source records](../configs/occupation-inputs.json), [Eurostat cube receipt](../configs/sector-hours-inputs.json).

## US workplace measures

| Employed civilian adults | September 2020 | September 2021 | September 2022 |
| --- | ---: | ---: | ---: |
| Telework because of pandemic | 22.64% | 13.21% | 5.17% |
| Unable to work because of closures or lost business | 7.14% | 2.17% | 0.67% |
| Actual complete responses per measure | 50,303 | 48,473 | 48,167 |

The three national telework differences against published BLS percentages were −0.065, +0.006 and −0.034 percentage points. All 144 estimate cells and 48 contrasts were replayed. Thirteen cells had insufficient support and were withheld. Thirty-nine contrasts had both endpoints. No participant keys or individual weights appear in public artifacts. [September 2020 comparator](https://www.bls.gov/news.release/archives/empsit_10022020.htm), [September 2021 comparator](https://www.bls.gov/news.release/archives/empsit_10082021.htm), [September 2022 comparator](https://www.bls.gov/news.release/archives/empsit_10072022.htm).

For professional occupations, pandemic telework changed from 39.79% to 8.42%. For service occupations it changed from 4.28% to 1.08%. Reported inability to work among employed people in leisure and hospitality changed from 14.63% to 0.89%. These estimates use separate September populations and do not capture workers who had already left employment by the survey. The UK mobility device series retains its separate population. Sampling design intervals are unavailable for these published CPS-derived cells. [Census extract method](https://www2.census.gov/programs-surveys/cps/techdocs/Covid19_TechDoc.pdf).

## European sector hours

The release covers 27 EU countries and nine activity categories, 2017 Q1 through 2024 Q4. The independent decoder verified 7,776 cube cells, 486 potential country-sector contrasts and 18 cohort summaries. It preserves missingness, definition changes, series breaks and low-reliability labels, including flags between the two endpoints.

| Hours in the main job per reference week | Q2 2019 to Q2 2020 median | Countries | Q2 2022 to Q2 2023 median | Countries |
| --- | ---: | ---: | ---: | ---: |
| All activities | −0.75 | 26 | −0.40 | 25 |
| Accommodation and food services | −3.05 | 26 | −0.30 | 25 |
| Information and communication | −0.80 | 25 | −0.60 | 25 |
| Human health and social work | +0.30 | 26 | −0.20 | 25 |

Twenty-two of 26 accommodation and food series fell at least one hour in 2020 Q2. One rose by at least one hour. The median difference between each matched country's accommodation change and its all-activities change was −2.6 hours. The two calendar-matched contrasts remain on separate sides of the 2021 survey redesign. Eurostat counts employed adults who actually worked in their main job during the reference week. This population leaves out employed people absent throughout that week. The separate OECD measure averages annual actual hours across employed persons. [Eurostat source and definitions](https://ec.europa.eu/eurostat/databrowser/view/lfsq_ewhan2/default/table), [EU-LFS methodology](https://ec.europa.eu/eurostat/statistics-explained/index.php?title=EU_Labour_Force_Survey_-_new_methodology_from_2021_onwards).

The study register now has 12 populated bounded analyses. Full acceptance still requires the timing, subgroup, calibration and integrated atlas checks.
