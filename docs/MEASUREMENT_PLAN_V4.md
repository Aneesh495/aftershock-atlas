# Work and education measurement protocol, version 4

Status: registered plan, not an implemented or verified result. The v0.2.0-preview, its scientific executable 1bd53f80841fe08c1bfd3a2fafb9c8d53b042cb0, original protocols and failed full profile remain preserved. This extension addresses missing measurements in S04, S08 and S09. It does not retune the already inspected forecast tests.

This is exploratory reconstruction and descriptive research. General published pandemic findings were consulted while checking feasibility. No blinded confirmation or causal effect of the pandemic is claimed. Freeze source bytes, resolved indicator definitions and eligibility before computing outcome comparisons. Retain failed acquisitions and unsupported comparisons.

## Work hours and real output

Resolve the current ILOSTAT table whose provider definition is mean weekly hours actually worked per employed person, with sex and economic-activity breakdowns where available. Freeze the table of contents, relevant dictionaries and resolved indicator code before downloading its observations. Never substitute usual hours, paid hours, hours per employee or aggregate total hours under the same label. Record original source identifiers, coverage, frequency, classification, status and methodological notes.

Preserve annual reference years 2010-2024. The primary contrasts are 2020 minus 2019 and 2022 minus 2019. These are calendar comparisons, not one universal lockdown or pandemic-end date. Retain separate source/definition/sex/sector series. Do not average competing sources or select a source because it gives a larger change. A matched contrast requires the same provider source and measurement definition at both endpoints, positive baseline hours for an indexed comparison, and no intervening documented break. Withhold uncertain pairings. Preserve all excluded keys and reasons.

Use total sex for primary country and sector comparisons. Additional source-defined sex contrasts remain separate. Compare sectors only at a common documented classification level. National surveys and modeled estimates keep different measurement kinds. Do not interpret a source's uncertainty or suppression flag as an observed zero. Source estimates with unreliable flags are withheld from primary contrasts and remain in the coverage inventory.

The descriptive hypothesis is that matched hours changes differ across places and sectors. Report absolute hours per employed person, 2019=100 indices, matched denominators and complete missingness. Compare with existing real GDP per person using its own index and the same country/year keys. GDP per person and hours per employed person do not identify aggregate hours loss, labor productivity or a causal output effect. Do not multiply an employment-to-population ratio by an all-age population to invent employed-person counts.

Primary summaries require at least five matched countries; smaller cohorts remain source tables without a pooled conclusion. Report exact finite-panel medians, ranges and direction counts. Publish provider uncertainty when available. When the source omits sampling errors, label measurement uncertainty unavailable and withhold formal country-change significance claims. Do not replace missing survey uncertainty with a bootstrap over countries. Record source-composition and break exclusions before discussing differences from mobility's opt-in device sample.

## Learning assessment cohorts

Acquire the official OECD PISA 2022 Annex B1 chapter 5 aggregate workbook linked by StatLink wh9d4z. Use the internally revised mathematics, reading and science means and source uncertainty for 2015, 2018 and 2022, where released. Retain the complete workbook and cell coordinates. No student, parent, teacher or school-level participant files are needed.

The primary estimand is the published education-system mean change from 2018 to 2022, separately by subject. A secondary comparison uses 2015 to 2018 and explicitly retains the different elapsed times. These are repeated cross-sectional cohorts of eligible 15-year-olds, not matched students. The postponed assessment, changing participation and enrollment, sampling standards, mode and linkage can alter comparability.

Preserve provider missingness codes and caution markers. Publish all released systems descriptively; the primary matched summary excludes systems carrying the provider's relevant sampling/comparability caution. Show the sensitivity including those systems. Keep education systems distinct from sovereign countries. Baku, UK constituent systems and other partial-country populations must not inherit a whole-country GDP identity. Resolve an explicit source-name/code crosswalk and retain unmatched systems.

Use provider-released change standard errors when they include the required cross-cycle/linking treatment. Reproduce mean changes from the source means and compare with the provider's released change table, allowing only the precision implied by published rounding. If only marginal mean standard errors are available, show their separate intervals and withhold a formal change interval until the linking/covariance contract is established. Never assume independent cycles to manufacture a trend standard error.

The reconstruction question is whether source-supported 2018-2022 changes, uncertainty and caution exclusions differ by system and subject. Retain improvements, declines and unresolved changes. Do not attribute them to school closure duration or remote learning policy. Prespecified significance tests, where provider change errors permit them, use two-sided normal approximation and Benjamini-Hochberg adjustment within subject across eligible systems, plus an explicit family label. No monolithic score combines subjects with GDP or work hours.

## Reported remote instruction in the US

Inspect only the frozen Census Household Pulse week 1 dictionary to resolve teaching, school-age-child eligibility, remote-instruction and teaching-time items. Commit the resolved item map and category/missing-code definitions before computing weighted outcomes. Use the existing lawful public-use ZIP, person weights and all 80 replicate weights. The previously published PHQ/GAD results and their two unresolved agreement failures remain unchanged.

The estimand is US adults in the source-defined eligible household group reporting each instruction arrangement or teaching-time category. Person weights estimate adults, not children or households. Do not relabel these estimates as student reach, attended instruction or learning attainment. Multiple-response arrangements may overlap and their percentages need not sum to 100. No pre-2020 matched comparison is invented.

Apply the registered SDR factor 4/80 to ratio-estimate replicate deviations. Preserve complete-case weighted denominators, eligible unweighted respondents, missing-item fractions, effective sample-size diagnostics and normal-approximation intervals with explicit design limits. Minimum disclosure support is 100 complete respondents per derived cell; suppression also removes derived intervals and denominators from public exports. Source-defined sex and age contrasts may be reported where supported. Unknown codes cause a failure rather than silent recoding.

Keep respondent identifiers and individual weights only in transient local processing. Publish only safe aggregate cells, source identities and independent aggregate replay. This is the same week 1 sample as the mental-health exercise, not an independent survey. Nonresponse sensitivity is assumption-dependent and cannot establish representativeness. Global learning cohorts and US household reports remain separate populations and schemas.

## Implementation, interface and independent checks

Each source gets a typed measurement contract, bounded parser, exclusion ledger, safe public tables and a useful atlas path. Add actual work-hours and learning/remote-instruction views with source, units, population, reference years, missingness and export provenance. Current-vintage measurements remain descriptive; they do not fill historical forecast inputs.

Independently parse the raw released fields or workbook cells. Reconstruct all matched comparisons, classification and source-break exclusions, provider uncertainty and multiplicity families. Recompute every released remote-instruction cell from the lawful person/replicate files without publishing them. Compare every displayed/exported measurement with its typed source table.

Execute rehashed semantic controls for hours-definition substitution, merged source/break populations, a shifted learning cycle or changed released mean, an invented trend error, and person-denominator reclassification. Preserve actual subprocess exits and intended rejection reasons. Existing source and history controls remain. An unavailable input or incomplete design stays incomplete in the full campaign.

## Resources and stopping rules

No paid compute or unattended jobs. Metadata requests are capped at 2 MB each; the learning workbook at 20 MB; an hours table at 40 MB compressed. Stream compressed data with a 250 MB expanded-byte cap and two-million-row cap. Do not materialize decompressed participant CSVs. Use existing bounded Arrow/DuckDB settings and atomic artifacts. Stop on a noncolliding identity failure, unknown schema, unknown code, incomplete source, nonfinite result, unsupported variance contract or the existing 5 GB project / 400 GB Mac-used limits.

Reserve at least twice the requested source cap before acquisition and 300 MB before feature/evidence construction. Sample storage during work. Deduplicate only SHA-verified identical archived copies with all paths and unique bytes preserved. Preserve prior released models and evidence. Each execution stage retains its ten-minute timeout and exact resume command.

## Primary references and access status

- [ILOSTAT bulk documentation](https://ilostat.ilo.org/data/bulk/) and [official interface documentation](https://ilostat.github.io/Rilostat/). The documented metadata CSV endpoint returned HTTP 200 with zero bytes during feasibility; no hours observations were accepted from that response.
- [ILO rights and permissions](https://www.ilo.org/rights-and-permissions). Apply the provider's data terms, attribution and exceptions; a software-package license does not license restricted microdata.
- [OECD PISA 2022 aggregate results](https://www.oecd.org/en/publications/pisa-2022-results-volume-i_53f23881-en/full-report/results-for-countries-and-economies_360c8f67.html) and [official chapter workbook StatLink](https://stat.link/wh9d4z).
- [OECD terms, data section](https://www.oecd.org/en/about/terms-conditions.html). Retain dataset-specific attribution and check additional third-party restrictions before redistribution. No OECD logo or endorsement claim.
- [Census Household Pulse public-use data](https://www.census.gov/programs-surveys/household-pulse-survey/datasets.html). Use the already pinned week 1 bytes and dictionary; never publish participant records.

The public World Bank school-survey repository currently contains metadata and placeholder files rather than the needed survey-response records in its master data tree. The UIS public data page also failed during feasibility. Neither is treated as an acquired remote-instruction dataset. This protocol uses the independently documented US household measure under its own limits.
