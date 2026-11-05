"""
Command Line Interface for promofinder.
Conforms strictly to project specifications
and project specifications
"""

from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

from promofinder.parser import parse_all_episodes
from promofinder.models import ms_to_time_str
from promofinder.pipeline import (
    run_requests_export,
    run_discovery_and_analysis,
    run_finalization_and_ranking,
)


def cmd_ingest(args: argparse.Namespace) -> int:
    """Ingests screenplays, parses scenes and events, and creates run manifest."""
    start_t = time.time()
    input_path = Path(args.input)
    run_dir = Path(args.run)
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Ingesting screenplays from '{input_path}'...")
    manifests = parse_all_episodes(input_path)
    total_events = sum(len(m.events) for m in manifests)
    total_duration = sum(m.duration_ms for m in manifests)
    total_regressions = sum(len(m.start_regressions) for m in manifests)

    # Save manifest
    manifest_data = {
        "run_id": run_dir.name,
        "input_directory": str(input_path),
        "episode_count": len(manifests),
        "total_events": total_events,
        "total_duration_ms": total_duration,
        "total_duration_formatted": ms_to_time_str(total_duration),
        "total_start_regressions": total_regressions,
        "episodes": [m.to_dict() for m in manifests],
    }
    manifest_file = run_dir / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    # Save parsed events
    all_events = []
    for m in manifests:
        for ev in m.events:
            all_events.append(ev.to_dict())

    events_file = run_dir / "events.json"
    with open(events_file, "w", encoding="utf-8") as f:
        json.dump(all_events, f, indent=2)

    events_jsonl_file = run_dir / "events.jsonl"
    with open(events_jsonl_file, "w", encoding="utf-8") as f:
        for ev in all_events:
            f.write(json.dumps(ev) + "\n")

    elapsed = time.time() - start_t
    timings_file = run_dir / "timings.json"
    timings = {}
    if timings_file.exists():
        with open(timings_file, "r", encoding="utf-8") as f:
            timings = json.load(f)
    timings["ingest"] = round(elapsed, 2)
    with open(timings_file, "w", encoding="utf-8") as f:
        json.dump(timings, f, indent=2)

    print(f"[+] Ingestion complete: {len(manifests)} episodes, {total_events} events in {elapsed:.2f}s.")
    print(f"[+] Saved manifest to {manifest_file}")
    print(f"[+] Saved events to {events_file} and {events_jsonl_file}")
    return 0


def cmd_requests(args: argparse.Namespace) -> int:
    """Exports structured prompt requests for all episodes."""
    run_dir = Path(args.run)
    run_requests_export(run_dir=run_dir, provider_name=args.provider)
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """Direct candidate discovery and validation across all episodes."""
    run_dir = Path(args.run)
    run_discovery_and_analysis(run_dir=run_dir, provider_name=args.provider)
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    """Deduplicates, selects Top-K diverse and Top 3 First-to-Post."""
    from promofinder.export import export_delivery_pack
    run_dir = Path(args.run)
    run_finalization_and_ranking(run_dir=run_dir, top_k=args.top_k)
    # Also package delivery pack
    export_delivery_pack(run_dir=run_dir)
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Computes evaluation metrics, baseline comparison, and run facts."""
    from promofinder.evaluate import run_evaluation
    run_dir = Path(args.run)
    run_evaluation(run_dir=run_dir)
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="promofinder",
        description="Short-form Promo Discovery & Ranking System",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest and parse screenplay files")
    p_ingest.add_argument("--input", "-i", required=True, help="Input directory of screenplay files")
    p_ingest.add_argument("--run", "-r", required=True, help="Run output directory (e.g. runs/demo)")
    p_ingest.set_defaults(func=cmd_ingest)

    # Subcommand: requests
    p_requests = subparsers.add_parser("requests", help="Generate analysis prompt requests")
    p_requests.add_argument("--run", "-r", required=True, help="Run output directory")
    p_requests.add_argument("--provider", default="manual", choices=["manual", "baseline"], help="Provider (manual, baseline)")
    p_requests.set_defaults(func=cmd_requests)

    # Subcommand: analyze
    p_analyze = subparsers.add_parser("analyze", help="Direct candidate discovery and analysis")
    p_analyze.add_argument("--run", "-r", required=True, help="Run output directory")
    p_analyze.add_argument("--provider", default="baseline", choices=["baseline", "manual"], help="Provider (baseline, manual)")
    p_analyze.set_defaults(func=cmd_analyze)

    # Subcommand: finalize
    p_finalize = subparsers.add_parser("finalize", help="Validate, deduplicate, and rank candidates")
    p_finalize.add_argument("--run", "-r", required=True, help="Run output directory")
    p_finalize.add_argument("--top-k", type=int, default=10, help="Number of top candidates to export")
    p_finalize.set_defaults(func=cmd_finalize)

    # Subcommand: evaluate
    p_eval = subparsers.add_parser("evaluate", help="Compute metrics and generate review report")
    p_eval.add_argument("--run", "-r", required=True, help="Run output directory")
    p_eval.set_defaults(func=cmd_evaluate)

    args = parser.parse_args()
    if hasattr(args, "func"):
        sys.exit(args.func(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
