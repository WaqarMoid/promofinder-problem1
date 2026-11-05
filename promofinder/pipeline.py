"""
Pipeline orchestration for promofinder.
Conforms strictly to project specifications
and project specifications
"""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from promofinder.models import (
    EpisodeManifest,
    EpisodeAnalysis,
    CandidateDraft,
    ValidatedCandidate,
    Event,
    Scene,
    parse_time_str_to_ms,
)
from promofinder.config import load_config
from promofinder.parser import parse_all_episodes
from promofinder.provider import (
    BaseProvider,
    ManualProvider,
    DeterministicBaselineProvider,
    parse_analysis_dict,
)
from promofinder.validate import validate_candidate_draft
from promofinder.rank import (
    deduplicate_candidates,
    select_and_rank_candidates,
    generate_top_3_rationales,
    export_candidates_to_csv,
    export_candidates_to_json,
)


def load_or_parse_manifests(run_dir: Path, input_dir: Optional[Path] = None) -> List[EpisodeManifest]:
    """Loads existing manifests from run directory or parses from input directory."""
    manifest_file = run_dir / "manifest.json"
    events_file = run_dir / "events.json"

    if manifest_file.exists() and events_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        with open(events_file, "r", encoding="utf-8") as f:
            events_data = json.load(f)

        events_by_ep: Dict[int, List[Event]] = {}
        for ev in events_data:
            ep = ev["episode"]
            if ep not in events_by_ep:
                events_by_ep[ep] = []
            events_by_ep[ep].append(
                Event(
                    event_id=ev["event_id"],
                    episode=ev["episode"],
                    scene_id=ev["scene_id"],
                    kind=ev["kind"],
                    speaker_raw=ev.get("speaker_raw"),
                    speaker_name=ev.get("speaker_name"),
                    start_ms=ev["start_ms"],
                    end_ms=ev["end_ms"],
                    start_str=ev["start_str"],
                    end_str=ev["end_str"],
                    text=ev["text"],
                    source_file=ev["source_file"],
                    source_line_start=ev["source_line_start"],
                    source_line_end=ev["source_line_end"],
                    source_order=ev["source_order"],
                )
            )

        manifests = []
        for ep_info in manifest_data["episodes"]:
            ep_num = ep_info["episode"]
            scenes = [
                Scene(
                    scene_id=s.get("scene_id", f"SCENE {idx+1:02d}"),
                    heading=s.get("heading", ""),
                    start_ms=s.get("start_ms", 0),
                    end_ms=s.get("end_ms", 0),
                    start_str=s.get("start_str", "00:00.00"),
                    end_str=s.get("end_str", "00:00.00"),
                    source_line=s.get("source_line", 0),
                )
                for idx, s in enumerate(ep_info.get("scenes", []))
            ]
            manifests.append(
                EpisodeManifest(
                    episode=ep_num,
                    file_path=ep_info["file_path"],
                    file_name=ep_info["file_name"],
                    sha256=ep_info["sha256"],
                    bytes_count=ep_info["bytes_count"],
                    line_count=ep_info["line_count"],
                    logline=ep_info["logline"],
                    continuity=ep_info["continuity"],
                    scenes=scenes,
                    events=events_by_ep.get(ep_num, []),
                    duration_ms=ep_info["duration_ms"],
                    start_regressions=ep_info.get("start_regressions", []),
                    warnings=ep_info.get("warnings", []),
                )
            )
        return manifests

    if input_dir:
        return parse_all_episodes(input_dir)

    raise FileNotFoundError(f"Neither manifest in {run_dir} nor input_dir provided.")


def run_requests_export(run_dir: Path, provider_name: str = "manual"):
    """Exports structured prompt requests for all 50 episodes."""
    manifests = load_or_parse_manifests(run_dir)
    requests_dir = run_dir / "requests"
    provider = ManualProvider(requests_dir=requests_dir)

    print(f"[*] Exporting prompt requests for {len(manifests)} episodes into {requests_dir}...")
    for m in manifests:
        provider.export_request(m)
    print(f"[+] All {len(manifests)} requests exported.")


def run_discovery_and_analysis(
    run_dir: Path,
    provider_name: str = "baseline",
    input_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Executes candidate discovery across all 50 episodes.
    Stores raw responses, validated candidates, and rejected candidates.
    """
    manifests = load_or_parse_manifests(run_dir, input_dir=input_dir)
    manifest_map = {m.episode: m for m in manifests}

    # Setup directories
    raw_dir = run_dir / "raw"
    validated_dir = run_dir / "validated"
    rejected_dir = run_dir / "rejected"
    raw_dir.mkdir(parents=True, exist_ok=True)
    validated_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    # Load optional config
    cfg = load_config()

    if provider_name in ("baseline", "heuristic"):
        provider: BaseProvider = DeterministicBaselineProvider()
    elif provider_name == "manual":
        provider = ManualProvider(requests_dir=run_dir / "requests", responses_dir=run_dir / "responses")
    elif provider_name == "api":
        raise NotImplementedError(
            "External cloud LLM integration is disabled in this deterministic local prototype. "
            "Supported providers: 'baseline', 'manual'."
        )
    else:
        raise ValueError(f"Unknown provider '{provider_name}'. Supported providers: 'baseline', 'manual'")

    print(f"[*] Executing candidate discovery across {len(manifests)} episodes using provider '{provider_name}'...")

    analyses: List[EpisodeAnalysis] = []
    all_validated_candidates: List[ValidatedCandidate] = []
    all_rejected_candidates: List[ValidatedCandidate] = []
    episode_status_counts = {"success": 0, "no_candidate": 0, "failed": 0}

    start_time = time.time()

    for m in manifests:
        analysis = provider.generate_analysis(m)

        # Validate candidate drafts
        ep_valid = []
        ep_rejected = []
        for draft in analysis.candidates:
            validated = validate_candidate_draft(
                draft=draft,
                manifest=m,
                run_id=run_dir.name,
                all_manifests_map=manifest_map,
            )
            if validated.is_valid:
                ep_valid.append(validated)
                all_validated_candidates.append(validated)
            else:
                ep_rejected.append(validated)
                all_rejected_candidates.append(validated)

        # Recompute episode status post-validation per Section 3.1
        if analysis.status in ("failed", "pending"):
            final_status = analysis.status
            final_reason = analysis.reason
        elif len(ep_valid) > 0:
            final_status = "success"
            final_reason = None
        else:
            final_status = "no_candidate"
            if not analysis.reason:
                final_reason = f"No candidate drafts survived hard eligibility validation (all {len(analysis.candidates)} drafts rejected)."
            else:
                final_reason = analysis.reason

        analysis.status = final_status
        analysis.reason = final_reason
        analyses.append(analysis)
        episode_status_counts[final_status] = episode_status_counts.get(final_status, 0) + 1

        # Save raw analysis with post-validation status
        with open(raw_dir / f"analysis_ep{m.episode:03d}.json", "w", encoding="utf-8") as f:
            json.dump(analysis.to_dict(), f, indent=2)

    elapsed = time.time() - start_time

    # Save all validated and rejected
    export_candidates_to_json(all_validated_candidates, validated_dir / "all_validated_candidates.json")
    export_candidates_to_json(all_rejected_candidates, rejected_dir / "all_rejected_candidates.json")

    # Save summary of analyses
    analyses_summary = {
        "run_id": run_dir.name,
        "provider": provider_name,
        "elapsed_sec": round(elapsed, 2),
        "total_episodes": len(manifests),
        "status_counts": episode_status_counts,
        "total_validated_candidates": len(all_validated_candidates),
        "total_rejected_candidates": len(all_rejected_candidates),
        "episodes": [
            {
                "episode": a.episode,
                "status": a.status,
                "reason": a.reason,
                "candidate_count": len(a.candidates),
            }
            for a in analyses
        ],
    }
    with open(run_dir / "discovery_summary.json", "w", encoding="utf-8") as f:
        json.dump(analyses_summary, f, indent=2)

    # Record stage timing
    timings_file = run_dir / "timings.json"
    timings = {}
    if timings_file.exists():
        with open(timings_file, "r", encoding="utf-8") as f:
            timings = json.load(f)
    timings["discovery"] = round(elapsed, 2)
    with open(timings_file, "w", encoding="utf-8") as f:
        json.dump(timings, f, indent=2)

    print(
        f"[+] Discovery complete: {episode_status_counts['success']} success, "
        f"{episode_status_counts['no_candidate']} no_candidate, {episode_status_counts['failed']} failed."
    )
    print(f"[+] Total validated candidates: {len(all_validated_candidates)}; rejected: {len(all_rejected_candidates)}")
    return analyses_summary


def run_finalization_and_ranking(
    run_dir: Path,
    top_k: int = 10,
) -> Dict[str, Any]:
    """
    Deduplicates candidates, ranks, selects Diverse Top-K and First-to-Post Top 3.
    Exports JSON and CSV deliverables.
    """
    fin_start_time = time.time()
    validated_file = run_dir / "validated" / "all_validated_candidates.json"
    if not validated_file.exists():
        raise FileNotFoundError(f"Missing validated candidates file: {validated_file}")

    with open(validated_file, "r", encoding="utf-8") as f:
        cands_raw = json.load(f)

    # Reconstitute ValidatedCandidate objects
    candidates: List[ValidatedCandidate] = []
    for c in cands_raw:
        from promofinder.models import ResolvedSegment
        segs = [
            ResolvedSegment(
                episode=s["episode"],
                start_event_id=s["start_event_id"],
                end_event_id=s["end_event_id"],
                start_ms=s["start_ms"],
                end_ms=s["end_ms"],
                start_time_str=s["start_time_str"],
                end_time_str=s["end_time_str"],
                duration_ms=s["duration_ms"],
                duration_sec=s["duration_sec"],
                event_ids=s["event_ids"],
                overlapping_event_ids=s.get("overlapping_event_ids", []),
                source_line_start=s.get("source_line_start", 0),
                source_line_end=s.get("source_line_end", 0),
            )
            for s in c["segments"]
        ]
        cand_obj = ValidatedCandidate(
            candidate_id=c["candidate_id"],
            run_id=c["run_id"],
            episode=c["episode"],
            is_stitched=c["is_stitched"],
            segments=segs,
            total_duration_ms=c["total_duration_ms"],
            total_duration_sec=c["total_duration_sec"],
            duration_valid=c.get("duration_valid", True),
            hook=c["hook"],
            hook_offset_ms=c.get("hook_offset_ms", 0),
            hook_complete_by_ms=c.get("hook_complete_by_ms", 0),
            hook_within_3s=c.get("hook_within_3s", True),
            cliffhanger=c["cliffhanger"],
            cliff_gap_ms=c.get("cliff_gap_ms", 0),
            cliff_near_end=c.get("cliff_near_end", True),
            boundary_conflicts=c.get("boundary_conflicts", 0),
            answer_events_after_cliff=c.get("answer_events_after_cliff", 0),
            segment_count=c.get("segment_count", len(segs)),
            max_duplicate_iou=c.get("max_duplicate_iou", 0.0),
            source_events_present=c.get("source_events_present", True),
            why_it_works=c.get("why_it_works", ""),
            theme=c.get("theme", ""),
            rank=c.get("rank", 0),
            rank_percentile=c.get("rank_percentile"),
            ranking_rationale=c.get("ranking_rationale", ""),
            posting_priority=c.get("posting_priority", "Standard"),
            standalone_summary=c.get("standalone_summary", ""),
            is_valid=c["is_valid"],
            validation_errors=c.get("validation_errors", []),
            validation_warnings=c.get("validation_warnings", []),
            risks=c.get("risks", []),
            join_reason=c.get("join_reason"),
        )
        candidates.append(cand_obj)

    print(f"[*] Finalizing and ranking {len(candidates)} candidates...")

    # 1. Deduplication
    deduped_candidates, suppressed_ids = deduplicate_candidates(candidates)
    print(f"[+] Deduplicated: {len(deduped_candidates)} retained, {len(suppressed_ids)} near-duplicates suppressed.")

    # 2. Sequential ranking across all candidates and Top-K diverse selection
    from promofinder.rank import select_and_rank_candidates
    ranked_all, top_diverse, substitutions = select_and_rank_candidates(
        deduped_candidates, top_k=top_k
    )

    # 3. Top 3 First-to-Post with evidence-backed trade-offs
    top_3_rationales = generate_top_3_rationales(top_diverse)

    # 4. Exports
    exports_dir = run_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    export_candidates_to_json(ranked_all, exports_dir / "ranked_all_candidates.json")
    export_candidates_to_csv(ranked_all, exports_dir / "ranked_all_candidates.csv")

    export_candidates_to_json(top_diverse, exports_dir / "top10_diverse_promos.json")
    export_candidates_to_csv(top_diverse, exports_dir / "top10_diverse_promos.csv")

    top3_file = exports_dir / "top3_first_to_post.json"
    with open(top3_file, "w", encoding="utf-8") as f:
        json.dump(top_3_rationales, f, indent=2)

    meta_summary = {
        "run_id": run_dir.name,
        "total_candidates": len(candidates),
        "deduped_candidates_count": len(deduped_candidates),
        "suppressed_near_duplicates_count": len(suppressed_ids),
        "top_diverse_count": len(top_diverse),
        "top_3_first_to_post": top_3_rationales,
        "diversity_substitutions": substitutions,
    }
    with open(exports_dir / "ranking_summary.json", "w", encoding="utf-8") as f:
        json.dump(meta_summary, f, indent=2)

    fin_elapsed = time.time() - fin_start_time
    timings_file = run_dir / "timings.json"
    timings = {}
    if timings_file.exists():
        with open(timings_file, "r", encoding="utf-8") as f:
            timings = json.load(f)
    timings["finalize"] = round(fin_elapsed, 2)
    with open(timings_file, "w", encoding="utf-8") as f:
        json.dump(timings, f, indent=2)

    print(f"[+] Exports generated in '{exports_dir}':")
    print(f"    - ranked_all_candidates.json / .csv")
    print(f"    - top10_diverse_promos.json / .csv")
    print(f"    - top3_first_to_post.json")
    print(f"    - ranking_summary.json")

    return meta_summary
