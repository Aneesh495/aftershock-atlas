# Release dates, boundaries and national survey context

## UK economic releases

The Office for National Statistics archive covers 18 quarters from 2021Q3 through 2025Q4. Direct workbook replay checked 846 quarterly level cells across 36 editions. A separate parser checked each workbook against the dated bulletin and verified 72 day-before and release-day joins. Growth rates compare two levels within one vintage so that a change in the currency base cannot masquerade as growth. Six bulletins include notices or corrections. Their notices concern commentary, other indicators, or GDP components outside this ABMI growth comparison.

Of 18 quarter pairs, two revisions reached the registered 0.25 percentage point threshold. Growth in 2021Q4 was revised from 0.96% to 1.28%. Growth in 2022Q2 was revised from −0.08% to 0.23%, the only strict sign change. These are published changes between editions, with no sampling precision claim. The join uses official end-of-day release dates. Monthly GDP releases and corrections within a day fall outside this reconstruction.

[ONS GDP workbook archive](https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi) · [Frozen public archive and checksums](https://github.com/Aneesh495/aftershock-atlas/releases/tag/v0.3.0-sources)

## Connecticut historical geography

The town-level Census join conserves 3,605,944 residents, reconciling 169 towns to eight historical counties and nine planning regions across 19 overlap pairs. Four zero-population water subdivisions account for five additional relationships. Seven old counties split across two or more regions. Residents are observed as of 1 April 2020. The change notice dates to 6 June 2022, the new TIGER geographic reference to 1 January 2022 and the TIGER release to 30 September 2022. Counties and county-equivalents are used differently across some ACS summary levels. A resident-population ratio does not assign county-only deaths by place of occurrence to a planning region.

[Census relationship file](https://www2.census.gov/geo/docs/reference/ct_change/ct_cou_to_cousub_crosswalk.txt) · [Planning-region population benchmarks](https://www2.census.gov/adrm/PDB/2024/2024_PDB_Documentation.pdf)

## Social context in separate mid-2021 waves

The analysis directly standardized two outcomes among US adults aged 25 and older using the NCHS standard and all 80 person replicates. The verifier recalculated 88 descriptive estimates and 52 contrasts across primary and age-boundary sensitivity analyses. Four descriptive estimates were withheld. Both unrestricted national food calculations agreed with the corresponding Census tables at the preregistered tolerance, with absolute differences below 0.000001 percentage points.

| Pulse week | Housing tenure contrast, renters minus owner-occupied | Income contrast, under $50,000 minus at least $50,000 |
| --- | ---: | ---: |
| 33 | 11.60 pp (95% interval 10.37 to 12.83) | 17.19 pp (15.64 to 18.74) |
| 34 | 10.28 pp (95% interval 8.75 to 11.81) | 15.02 pp (13.66 to 16.39) |

The table measures seven-day household food insufficiency reported by adults. Both contrasts remained positive after excluding ages near the age-band cutoffs. The weighted household response rates were 6.3% and 6.1%. The estimates therefore retain possible selection bias. Income refers to 2019 in the earlier wave and 2020 in the later wave. The symptom items change recall from seven to fourteen days. Both waves are kept separate. The geographic and historical release checks cover these sources only. Data outside their boundaries and multinational forecast undercoverage remain open.

[Census week 33](https://www.census.gov/data/tables/2021/demo/hhp/hhp33.html) · [Census week 34](https://www.census.gov/data/tables/2021/demo/hhp/hhp34.html) · [NCHS age standard](https://www.cdc.gov/nchs/hus/sources-definitions/age-adjustment.htm)
