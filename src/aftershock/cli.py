"""Every build target invokes real work or fails with a concrete missing dependency."""
from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="aftershock")
    parser.add_argument("command", choices=["doctor", "data", "covid-data", "panel", "fit", "forecasts", "causal",
        "studies", "atlas", "demo", "bench", "stress", "docs", "acceptance", "verify", "release", "biology", "surveys"])
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
