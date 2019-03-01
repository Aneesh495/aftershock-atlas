# Build status

Status: working research preview. Full acceptance is incomplete.

Executable source: `8bd15fb2e9110197f32cf84ada81fd0b533c4371`.

The source was pushed, cloned from GitHub into a clean isolated checkout, and executed with frozen input bytes. The diagnostic bundle is `evidence/release-clean-20261111`. Full profile `evidence/release-full-20261111` returned exit 1 and preserved incomplete gate evidence.

The diagnostic independently checked 209,894 measurement records, 68,570 predictions, 12,370 score groups, 175 joint multiyear economies, 174 saved-model predictions, four age contrasts and twenty released genetic probes. Fourteen subprocess mutations were rejected for their intended reasons. Thirty-one correctness and integration tests passed.

The exploratory extension separately replayed 6,857 dynamic predictions, their 1,237 score groups and 24 Census design cells from 74,413 public-use respondents with 80 replicate weights. No respondent records enter evidence or the website. Twenty-two of 24 point comparisons met the prespecified tolerance; the failures remain visible. All 18 model starts converged, but the dynamic model lost on three families. See [extension results](EXTENSION_RESULTS.md).

Hosted engineering checks and Pages deployment passed for the executable source: [workflow run](https://github.com/Aneesh495/aftershock-atlas/actions/runs/43133290855). This workflow does not certify full scientific acceptance.

| Gate | Full-profile status | Evidence and limitation |
| --- | --- | --- |
| G01 | passed | 22 frozen sources; metric-level coverage |
| G02 | blocked | Only identity geography crosswalks and current-vintage annual inputs; full historical as-of parity unavailable |
| G03 | passed | Independent source-parser, matched annual denominators and direct age-standardization replay |
| G04 | passed | 230 surveillance countries; real multiyear health and economic panel |
| G05 | passed | WHO 2022 and 2023 modeled excess releases, input support and changed age bands retained |
| G06 | blocked | Week 1 design weights, 80 replicates and nonresponse scenarios replayed; later-wave auditing remains incomplete |
| G07 | blocked | GDP and enrollment run; hours, remote instruction and learning assessments absent |
| G08 | unverified | Provider-released US subgroup estimates retain labels and suppression; independent subgroup denominator audit incomplete |
| G09 | passed | Real HGI technical harmonization and archived CDC weighted lineage estimates; shared sample and LD limits explicit |
| G10 | blocked | 60 configurations and three trained seeds; strict historical-vintage forecast campaign unavailable |
| G11 | passed | Real candidate group-time analyses, pretrends, pseudo-onsets and unsupported cells |
| G12 | blocked | 12 executed tables, 4 with incomplete outcome or design support |
| G13 | unverified | Atlas implementation exists; interactive source-frozen final walkthrough must be reviewed |
| G14 | passed | Shared disclosure boundary, provider flags and export checks |
| G15 | passed | Bounded acquisitions, checkpoint resume and measured storage accounting |
| G16 | unverified | Requires recorded semantic negative-control subprocesses on this exact source |

## Exact replay

```sh
make verify EVIDENCE=evidence/release-clean-20261111 EXPECTED_SOURCE=8bd15fb2e9110197f32cf84ada81fd0b533c4371
```

Use the explicit executable source when the branch contains later report-only commits. The verifier checks runtime files against that source, parses the frozen bytes, and never replaces absent work.

## Remaining work

Complete historical availability and geographic crosswalk validation, complete multiwave survey-weight and nonresponse auditing, richer lawful subgroup denominator checks, working-hours and learning-assessment measurement, the full scientific campaign. Current Gaussian and count-model intervals under-cover during the pandemic. Eight studies have bounded support and four remain incomplete in outcome or design coverage. These gaps cannot be closed by presentation or diagnostic checks.

The [requirement and artifact map](COVERAGE_GAPS.md) also identifies absent tests, hospital/ICU, COVID vaccine-rollout, sector, hours, remote-instruction and learning-assessment measurements. G16 passed in the separate source-matched diagnostic. The full-profile bundle exits before its own tamper stage and retains that gate as unverified; it is not relabeled as a full pass. The original executable and results remain in the v0.1.0-preview tag and frozen local checkout.
