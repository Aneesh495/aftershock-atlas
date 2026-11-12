# Evidence bundle format

A bundle is a new directory identified by a caller-supplied run ID. `SOURCE_INPUTS.json` records the exact executable Git revision and per-file hashes. `DATASETS.json` records frozen upstream identities and source rights. `ENVIRONMENT.json` records CPU, precision, dependencies and storage. `COMMANDS.jsonl` contains actual subprocess argv, exits, durations and log identities. `MANIFEST.json` hashes every included artifact. `ACCEPTANCE.json` preserves the profile and individual domain gates.

The raw observation CSV contains every surveillance and annual measurement used by the forecast core. Frozen WHO, registry and World Bank bytes are included for independent parsing. Survey, excess, causal, genetics, lineage and subnational tables retain their own measurement schemas. Saved initial and trained parameters, preprocessing populations, feature arrays, test identities and frozen replay probes support bounded parameter replay without retraining.

The verifier is implemented separately in `verification.py`. It reads trusted source file identities from Git, rather than trusting the bundle's own declared commit. It independently parses upstream values, detects duplicate populations and forged timestamps, reconstructs features from earlier annual records, recomputes proper scores, verifies age-standardized rates, checks genetic effect directions and validates suppression. A good hash does not prove a scientific result.

`negative-controls.json` records real subprocess invocations and rejection reasons. Semantic mutations are rehashed before invoking the same verifier. Controls include forged vintage, duplicate population, future feature year, invalid genetic sign, shifted placebo and shared-sample reclassification. Additional controls cover corruption, missing artifacts, source mismatch, failed saved-model replay, source-defined survey category reclassification, survey variance factors and denominators, and saved dynamic parameters. The test must reject for the intended reason.

Diagnostic verification establishes these executed invariants. It does not establish complete scientific acceptance. Full profile verification rejects any incomplete domain gate. No required skip, timeout, empty workload or nonfinite result is silently accepted.

The historical extension adds `HISTORY_INPUTS.json`, 43 public aggregate raw partitions, the typed archived panel, revision and endpoint-sensitivity tables, six prediction partitions and saved historical model parameters. Its independent parser reconstructs every archived cell, within-edition GDP anchor and feature. The original core now replays all eligible test rows rather than a small probe subset. The 19-control source recipes include later-edition substitution, forged month bounds, future-feature injection, changed GDP anchors and forged full-pass flags. A source recipe is distinct from an executed rejection receipt.

The full campaign runs available semantic checks and actual tamper subprocesses before reporting missing scope. `VERIFICATION.json` may record `source_checks_passed_full_incomplete`; that status retains `profile=full` and `full_acceptance=false`. `FULL_INCOMPLETE.json` and exit 1 preserve the unresolved gates. The public `verify` command remains strict and returns nonzero for that same bundle. Trusted `configs/full-scope.json` prevents saved gate booleans from asserting capabilities absent from the executable.

## Claim-to-evidence ledger

| Claim | Owning mechanism | Replay artifact |
| --- | --- | --- |
| Real surveillance and annual values match frozen inputs | `panel.py`, independent parser in `verification.py` | `observations.csv`, `raw/`, `DATASETS.json` |
| No duplicate measurement population | panel key uniqueness and independent set membership | observation identities |
| Features precede labels | chronological feature builder and raw-source reconstruction | `models/replay-inputs.npz`, `models/replay-keys.json` |
| Parameters learned from random initialization | analytic gradients, Adam and checkpoint movement | `models/seed-*/initial.npz`, `best.npz`, training histories |
| Held-out scores match predictions | independent Gaussian score recomputation | `predictions.json`, `fit.json` |
| Direct age rates match age-specific denominators | independent weighted-rate sum | `age-replay.json`, S03 table |
| Genetic odds ratios preserve effect signs | effect allele contracts and exponential replay | `genetics.json` |
| Survey suppression survives publication | shared disclosure boundary and public-cache test | `surveys.json` |
| Actual browser paths work | retained DOM observations and screenshots | `docs/media/browser-checks.json` |
| Full acceptance remains incomplete | explicit gate statuses and nonzero full profile | `FULL_INCOMPLETE.json`, build status |

The extension stores only safe aggregate survey cells and `SURVEY_INPUTS.json` source identities in a bundle. Its independent verifier reacquires or reads the exact public-use ZIP in ignored local storage. Raw participant records are never copied into evidence. [The public receipt](PREVIEW_EVIDENCE.json) links exact-source diagnostic results, fourteen actual rejection receipts and the separately failed full profile.
