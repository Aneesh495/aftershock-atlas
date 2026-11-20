# US surveillance source protocol

This extension plans three state-level source series and a survey bridge. Freeze definitions and source bytes before computing outcome comparisons. Current frozen values support retrospective descriptions.

| Source | Observable | Main comparison |
| --- | --- | --- |
| HHS state hospital capacity | Confirmed COVID admissions and ICU occupancy or reporting-facility denominators where supplied | Same-geography weekly burden and reporting completeness |
| HHS laboratory testing | PCR results by reported outcome and source-defined time | Positivity among reported positive and negative results, with inconclusive results preserved separately |
| CDC jurisdiction vaccination | Cumulative primary-series completion count and provider percent | Within-jurisdiction published coverage and signed report-to-report corrections |
| Census Household Pulse | Week 33 and 34 adult anxiety and depression responses and design weights | Separate estimates immediately before and after the instrument change |

The US sources cover the 50 states and DC where available. Preserve exact state and date populations and exclude US aggregates, territories and federal reporting organizations from state joins. A reported zero remains distinct from an empty value. Record original date semantics for each metric. Hospital admissions are flows and occupied ICU beds are stocks. Sum complete admission windows and average reported daily stocks. Keep contributor counts when supplied and withhold ratios when numerator and denominator coverage differs. Publish partial-window counts separately. Calculate weekly PCR positivity from summed counts, while retaining inconclusive results and auditing negative revisions. Positivity describes test results and selection into testing. Mark provider vaccination caps or missing percentages, respect cumulative report vintages, and retain negative revisions.

Keep health events, reporting dates and source captures distinct. The sources can support comparative reporting examples. They cannot identify infections, vaccination effects or causal temperature, mobility or policy effects. Preserve provider changes and use end-of-availability flags for discontinued sources. Exact state boundaries and definitions must be resolved against the source before joining.

The week 33 and 34 survey bridge uses respondent and 80 replicate weights from each public-use release, after resolving the source labels and methods. Analyze the two releases separately. A 7-day question and a 14-day question define different estimands. Report within-wave estimates, replicate intervals, item-nonresponse bounds and provider unit response rates, with no pooled mean, paired difference or attributable effect at the boundary. Compare aggregate estimates against released CDC/NCHS tables when matching construct and population are available. Keep participant rows in local protected workspace storage. Publish only aggregates that meet the registered disclosure criteria.

Use bounded serial data acquisition or at most three concurrent metadata requests. Cap each public-use ZIP at 85 MB compressed and 250 MB expanded. Stream the dictionary and two CSV members without persisting uncompressed participant records. Cap each selected state aggregate source at 25 MB and require explicit completeness checks and stable ordering. Store source SHA-256 identities for panels and independent verification. Execute test cases for missing versus zero, withheld ratios, inaccurate date labels, negative corrections and forged survey denominator or recall period.

Primary references are [HHS state hospital reporting](https://healthdata.gov/d/g62h-syeh), [HHS PCR testing](https://healthdata.gov/d/j8mb-icvb), [CDC jurisdiction vaccination](https://data.cdc.gov/d/unsk-b7fc) and the [Census 2021 PUF releases](https://www.census.gov/programs-surveys/household-pulse-survey/data/datasets.2021.html).
