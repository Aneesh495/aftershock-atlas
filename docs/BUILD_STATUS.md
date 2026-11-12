# Build status

Status: working research preview. Full acceptance is incomplete.

Executable source: `1bd53f80841fe08c1bfd3a2fafb9c8d53b042cb0`. The source was pushed, cloned from GitHub into a clean isolated checkout, and executed with frozen input bytes. No model checkpoints were copied into the fresh checkout before its first fit.

Diagnostic `history-final-clean-20261112` passed. It independently checked 209,894 core measurement records, 68,570 core prediction scores, 12,370 core score groups and all 20,571 eligible trained core network predictions. The historical exercise separately reconstructed 227,850 archived cells, 27,342 revision comparisons, 7,812 endpoint-sensitivity cells, 4,001 feature rows and all 42,097 historical predictions across 66 configurations. The 6,857 dynamic predictions and 24 Census design cells retain their separate exploratory protocol. Thirty-six correctness and integration tests passed. Nineteen actual subprocess tamper cases were rejected for their intended reasons.

Full profile `history-final-full-20261112` completed all eleven stages, independent checks and its own nineteen tamper subprocesses, then returned CLI exit 1. Its verification status is `source_checks_passed_full_incomplete`, with `profile=full` and `full_acceptance=false`. Required scientific gaps remain. [Public receipts](PREVIEW_EVIDENCE.json) preserve exact sources, workload counts, command exits and rejection reasons. [Linux engineering CI](https://github.com/Aneesh495/aftershock-atlas/actions/runs/43251027119) passed; it does not certify full scientific acceptance.

| Gate | Full-profile status | Evidence and limitation |
| --- | --- | --- |
| G01 | passed | 22 core, 2 survey and 43 historical input partitions; metric-level coverage and separate rights |
| G02 | blocked | Official archive-month editions present; original cell release-day and historical territory validation incomplete |
| G03 | passed | Independent source-parser, matched annual denominators and direct age-standardization replay |
| G04 | passed | 230 surveillance countries; real multiyear health and economic panel |
| G05 | passed | WHO 2022 and 2023 modeled excess releases, input support and changed age bands retained |
| G06 | blocked | Week 1 replicate weights and nonresponse sensitivity replayed; later-wave design auditing remains incomplete |
| G07 | blocked | GDP and enrollment run; hours, remote instruction and learning assessments absent |
| G08 | unverified | Provider-released US subgroup estimates retain labels and suppression; independent subgroup denominator audit incomplete |
| G09 | passed | Real HGI technical harmonization and archived CDC weighted lineage estimates; shared sample and LD limits explicit |
| G10 | blocked | 60 original configurations plus 66 archive configurations; release-day proof and pandemic calibration remain incomplete |
| G11 | passed | Real candidate group-time analyses, pretrends, pseudo-onsets and unsupported cells |
| G12 | blocked | 12 executed tables, 4 with incomplete outcome or design support |
| G13 | unverified | Atlas implementation exists; interactive source-frozen final walkthrough must be reviewed |
| G14 | passed | Shared disclosure boundary, provider flags and export checks |
| G15 | passed | Bounded acquisitions, checkpoint resume and measured storage accounting |
| G16 | passed | 19 actual source-matched semantic and structural tamper subprocesses rejected |

## Exact replay

```sh
make verify EVIDENCE=evidence/history-final-clean-20261112 EXPECTED_SOURCE=1bd53f80841fe08c1bfd3a2fafb9c8d53b042cb0
```

The strict public verifier returns nonzero for `history-final-full-20261112`. Available source checks still executed before that final domain-gate rejection. Use the explicit executable source after report-only commits. The verifier checks runtime files against the trusted Git source, parses frozen bytes and never replaces absent work.

## Remaining work

The [v0.2.0-preview release](https://github.com/Aneesh495/aftershock-atlas/releases/tag/v0.2.0-preview) is published. Its four original assets were downloaded or restored and byte-verified. The remote historical snapshot restored all 43 partitions. The public Pages walkthrough checked the frozen executable identity through downloaded CSVs, the full integrated path and 390 px / 1280 px layouts. [Publication receipts](RELEASE_RECEIPT_V3.json) and [offline thesis](paper/README.md) preserve this narrower verified outcome. These publication checks do not promote an incomplete scientific gate.

Complete original cell publication-day and territorial validation, later-wave survey design/nonresponse and subgroup denominator auditing, hours and learning measurement, pandemic uncertainty calibration and the four partially supported studies. The atlas has bounded verified user paths, but missing required domains prevent full G13 acceptance. Historical mortality and life-expectancy cohorts only support 2022, and their nominal 90 percent learned intervals cover only about one quarter and one fifth of targets. These failures remain visible in the [historical report](HISTORICAL_RESULTS.md) and model tables.

The [requirement and artifact map](COVERAGE_GAPS.md) also records absent tests, hospital/ICU, COVID vaccine-rollout, sector and remote-instruction measurements. The original v0.1.0-preview and v0.1.1-preview sources and evidence remain preserved. No diagnostic, model-count increase or presentation change closes these scientific requirements.
