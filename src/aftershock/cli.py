"""Every build target invokes real work or fails with a concrete missing dependency."""
from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="aftershock")
    parser.add_argument("command", choices=["doctor", "data", "covid-data", "panel", "fit", "forecasts", "causal",
        "studies", "atlas", "demo", "bench", "stress", "docs", "acceptance", "verify", "release", "biology", "surveys", "survey-data", "dynamic", "history-data", "history-panel", "history-fit", "history-atlas", "measurement-data", "measurement", "surveillance-data", "surveillance", "survey-bridge-data", "survey-bridge", "sector-hours-data", "sector-hours", "occupation-data", "occupation", "ct-crosswalk-data", "ct-crosswalk", "chronology-data", "uk-vintages", "social-context-data", "social-context", "uk-forecast", "territory-audit", "mortality-calibration"])
    parser.add_argument("--run-id", default="diagnostic")
    parser.add_argument("--profile", choices=["diagnostic", "full"], default="diagnostic")
    parser.add_argument("--evidence")
    parser.add_argument("--expected-source")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    try:
        command = args.command
        if command == "doctor":
            from .resources import doctor
            result = doctor()
        elif command in {"data", "covid-data"}:
            from .acquire import acquire
            data = acquire(args.refresh, only=["who", "regions", "wb_population"] if command == "covid-data" else None)
            result = {k: v["status"] for k, v in data.items()}
            if any(v == "blocked" for v in result.values()):
                print(json.dumps(result, indent=2))
                return 1
        elif command == "chronology-data":
            from .chronology import restore_chronology
            result = restore_chronology()
        elif command == "uk-vintages":
            from .uk_vintages import build_uk
            data = build_uk()
            result = {"editions": len(data["editions"]), "origin_checks": len(data["as_of"])}
        elif command == "mortality-calibration":
            from .mortality_calibration import build_mortality_calibration
            data = build_mortality_calibration()
            result = {"countries": len(data["cohorts"]["test"]), "prediction_rows": len(data["predictions"])}
        elif command == "territory-audit":
            from .territory_audit import build_territory_audit
            from .verify_territory_audit import verify_territory
            data = build_territory_audit()
            result = verify_territory(data, data["source"])
        elif command == "uk-forecast":
            from .uk_forecast import build_uk_forecast
            data = build_uk_forecast()
            result = {"models": len(data["scores"]), "origin_count": len(data["origins"]),
                      "selected_ridge": data["development"]["selected_ridge"]}
        elif command == "social-context-data":
            from .social_context import acquire_context
            result = acquire_context()
        elif command == "social-context":
            from .social_context import build_context
            data = build_context()
            result = {"waves": len(data["waves"]), "cells": sum(len(w["rows"]) for w in data["waves"].values())}
        elif command == "ct-crosswalk-data":
            from .ct_crosswalk import acquire_ct
            result = acquire_ct()
        elif command == "ct-crosswalk":
            from .ct_crosswalk import build_ct
            from .verify_ct_crosswalk import verify_ct
            data = build_ct()
            result = verify_ct(data, data["source"])
        elif command == "sector-hours-data":
            from .sector_hours import acquire_sectors
            result = acquire_sectors()
        elif command == "sector-hours":
            from .sector_hours import run_sectors
            data = run_sectors()
            result = {"source": data["source"], "quarters": len(data["observations"]), "comparisons": len(data["comparisons"])}
        elif command == "occupation-data":
            from .occupational_work import acquire_occupation
            result = acquire_occupation()
        elif command == "occupation":
            from .occupational_work import run_occupation
            data = run_occupation()
            result = {"source": data["source"], "periods": list(data["periods"]), "comparisons": len(data["comparisons"])}
        elif command == "survey-bridge-data":
            from .survey_bridge import acquire_bridge
            result = acquire_bridge()
        elif command == "survey-bridge":
            from .survey_bridge import run_bridge
            data = run_bridge()
            result = {"source": data["source"], "waves": {k: len(v["rows"]) for k, v in data["waves"].items()}}
        elif command == "surveillance-data":
            from .state_surveillance import acquire_surveillance
            result = acquire_surveillance()
        elif command == "surveillance":
            from .state_surveillance import build_surveillance
            data = build_surveillance()
            result = {"source": data["source"], "jurisdictions": len(data["states"]), "coverage": data["summary"]}
        elif command == "measurement-data":
            from .measurement import acquire_measurement
            result = acquire_measurement()
        elif command == "measurement":
            from .measurement import run_measurement
            result = run_measurement()
        elif command == "history-atlas":
            from .history_atlas import export_history
            result = export_history()
        elif command == "history-fit":
            from .history_fit import fit_history
            result = fit_history()
        elif command == "history-data":
            from .history import acquire_history
            result = acquire_history(args.refresh)
        elif command == "history-panel":
            from .history import build_history
            result = build_history()
        elif command == "survey-data":
            from .survey_design import acquire_design
            result = acquire_design(args.refresh)
        elif command == "dynamic":
            from .dynamic import fit_dynamic
            result = fit_dynamic()
        elif command == "panel":
            from .panel import build_panel
            result = build_panel()
        elif command == "fit":
            from .forecast import fit_models
            result = fit_models()
        elif command == "forecasts":
            from .forecast import no_shock_forecasts
            from .subnational import subnational_studies
            result = {"annual": no_shock_forecasts(), "subnational": subnational_studies()}
        elif command == "causal":
            from .causal import candidate_causal
            data = candidate_causal()
            result = {"cohorts": data["adoption_counts"], "identification": data["identification"], "cells": len(data["cells"])}
        elif command == "biology":
            from .genetics import host_genetics
            from .lineages import analyze_lineages
            data = host_genetics()
            result = {"host_aligned": data["aligned_variants"], "viral": analyze_lineages()}
        elif command == "surveys":
            from .survey import analyze_surveys
            result = analyze_surveys()
        elif command == "studies":
            from .excess import analyze_excess
            from .genetics import host_genetics
            from .lineages import analyze_lineages
            from .mobility import analyze_mobility
            from .studies import run_studies
            from .survey import analyze_surveys
            analyze_excess()
            host_genetics()
            analyze_lineages()
            analyze_mobility()
            analyze_surveys()
            from .measurement import RESULT, run_measurement
            from .io import read_json, source_commit
            if not RESULT.exists() or read_json(RESULT)["source"] != source_commit():
                run_measurement()
            from .survey_bridge import RESULT as BRIDGE_RESULT, run_bridge
            if not BRIDGE_RESULT.exists() or read_json(BRIDGE_RESULT)["source"] != source_commit():
                run_bridge()
            from .sector_hours import RESULT as SECTOR_RESULT, run_sectors
            from .occupational_work import RESULT as OCCUPATION_RESULT, run_occupation
            if not SECTOR_RESULT.exists() or read_json(SECTOR_RESULT)["source"] != source_commit():
                run_sectors()
            if not OCCUPATION_RESULT.exists() or read_json(OCCUPATION_RESULT)["source"] != source_commit():
                run_occupation()
            result = run_studies()
        elif command == "atlas":
            from .atlas import export_atlas
            result = export_atlas()
        elif command == "demo":
            from .server import serve
            serve(args.port)
            return 0
        elif command == "verify":
            from .verification import verify_bundle
            if not args.evidence or not args.expected_source:
                raise ValueError("Verification requires --evidence and independently supplied --expected-source")
            result = verify_bundle(args.evidence, args.expected_source)
        else:
            from .campaign import dispatch
            result = dispatch(args)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except KeyboardInterrupt:
        print("Interrupted; successful source partitions and atomic checkpoints are retained", file=sys.stderr)
        return 130
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        print(f"aftershock: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
