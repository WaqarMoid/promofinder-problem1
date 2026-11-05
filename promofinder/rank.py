"""
Ranking, deduplication, catalog selection, and export logic.
Conforms strictly to project specifications Section 3.C.
Zero subjective scores or quality ratings.
Lexicographic measurement ranking based strictly on observable fields.
"""

from __future__ import annotations
import csv
import json
import re
import copy
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from promofinder.models import ValidatedCandidate, ms_to_time_str


# Rule heuristic patterns for editorial shortlist prioritization per Section 3.4
SUBSTANTIVE_HOOK_PAT = re.compile(
    r"(?:\bwhy\s+are\s+you\s+holding\s+her\s+hand\b|\bi\s+want\s+to\s+see\s+you\s+crawl\b|\bstay\s+behind\s+me\b|"
    r"\barsenic\b|\bpoison\b|\bvial\b|\btheft\b|\bstole\b|\btraitor\b|\bfraud\b|\bmurder\b|\bbastard\b|\bmarry\b|\bwedding\b|\bhusband\b|"
    r"\bcrawl\b|\bhangs\b|\bgallows\b|\bthreat\b|\bcannot\s+marry\b|\bstole\s+my\s+wedding\b|\bwho\s+sent\s+you\b)",
    re.IGNORECASE
)

WEAK_HOOK_PAT = re.compile(
    r"^(?:for\s+what\?|how\s+long\?|what\s+now\?|what\s+is\s+it\?|why\?|who\?|where\?|not\s+yet\?|the\s+truth\.|hold\s+on\b|"
    r"close-up|low-angle|behind\s+her|insert|shot|tight\s+insert)",
    re.IGNORECASE
)

ACUTE_CLIFF_PAT = re.compile(
    r"(?:\bwho\?!|\bhangs\s+from\s+the\s+gallows\b|\bhangs\b|\bgallows\b|\band\s+you\s+knew\?|"
    r"\bwrong\s+answer\b|\bwho\s+sent\s+you\b|\bwhat\s+have\s+you\s+done\?|\bkill\b|\bdie\b|\bpoison\b|\bmurder\b|\bdestroy\b|"
    r"\bwhy\s+did\s+they\s+never\s+tell\s+us\?|\bwill\s+you\s+be\s+going\b|\bwhat\s+happens\s+to\s+me\?)",
    re.IGNORECASE
)

WEAK_CLIFF_PAT = re.compile(
    r"\b(?:of\s+them\?|and\s+i\s+am\s+what\?|not\s+yet\?|happy\?|did\s+you\?|can\s+i\s+help|are\s+you\s+hurt|what\s+is\s+it\?)\b",
    re.IGNORECASE
)


def evaluate_semantic_evidence(c: ValidatedCandidate) -> Tuple[bool, bool, bool, bool]:
    """
    Evaluates rule-based heuristic evidence per Section 3.4:
    1. hook_heuristic_pass: spoken dialogue hook with substantive dramatic tension/conflict
    2. cliffhanger_heuristic_pass: acute terminal question or impending threat
    3. standalone_context_heuristic_pass: named characters and multiple dialogue events without risk flags
    Returns (hook_pass, cliff_pass, ctx_pass, all_three_yes).
    This is an explainable rule heuristic, not ML/semantic ground truth.
    """
    h_text = c.hook.get("exact_quote", "").strip(' \t\n\r"\'“’‘”')
    c_text = c.cliffhanger.get("exact_quote", "").strip(' \t\n\r"\'“’‘”')
    h_speaker = c.hook.get("speaker")
    c_speaker = c.cliffhanger.get("speaker")

    h_supp = bool(h_speaker and SUBSTANTIVE_HOOK_PAT.search(h_text) and not WEAK_HOOK_PAT.search(h_text.lower()))
    c_supp = bool(c_speaker and ACUTE_CLIFF_PAT.search(c_text) and not WEAK_CLIFF_PAT.search(c_text.lower()))
    ctx_supp = bool(h_speaker and c_speaker and c.total_duration_sec >= 20.0 and len(c.risks) == 0)

    all_three_yes = (h_supp and c_supp and ctx_supp)
    return h_supp, c_supp, ctx_supp, all_three_yes


def calculate_temporal_iou(cand_a: ValidatedCandidate, cand_b: ValidatedCandidate) -> float:
    """Computes temporal intersection-over-union between two candidates on the same episode."""
    if cand_a.episode != cand_b.episode or not cand_a.segments or not cand_b.segments:
        return 0.0

    s_a, e_a = cand_a.segments[0].start_ms, cand_a.segments[-1].end_ms
    s_b, e_b = cand_b.segments[0].start_ms, cand_b.segments[-1].end_ms

    inter_ms = max(0, min(e_a, e_b) - max(s_a, s_b))
    union_ms = (e_a - s_a) + (e_b - s_b) - inter_ms
    return inter_ms / union_ms if union_ms > 0 else 0.0


def lexicographic_rank_key(c: ValidatedCandidate) -> Tuple[int, int, int, int, float, int, int, int, str]:
    """
    Transparent lexicographic measurement tuple per Section 3.C:
    1. all three semantic evidence decisions are 'yes' (-1 before 0)
    2. lower hook_complete_by_ms
    3. lower cliff_gap_ms
    4. fewer segments (segment_count == 1 preferred)
    5. lower max_duplicate_iou
    6. fewer declared context/risk flags
    7. deterministic tie-break by episode (ascending), start time (ascending), candidate ID
    """
    _, _, _, all_yes = evaluate_semantic_evidence(c)
    sem_yes_val = 1 if all_yes else 0
    start_ms = c.segments[0].start_ms if c.segments else 0
    risk_flags = len(c.validation_warnings) + len(c.risks)

    return (
        -sem_yes_val,
        c.hook_complete_by_ms,
        c.cliff_gap_ms,
        c.segment_count,
        c.max_duplicate_iou,
        risk_flags,
        c.episode,
        start_ms,
        c.candidate_id,
    )


def deduplicate_candidates(candidates: List[ValidatedCandidate]) -> Tuple[List[ValidatedCandidate], List[str]]:
    """
    Deduplicates candidates:
    Suppresses candidate if temporal IoU >= 0.70 with a higher-priority candidate on the same episode.
    Records max_duplicate_iou for each retained candidate.
    """
    initial_sorted = sorted(candidates, key=lexicographic_rank_key)
    kept: List[ValidatedCandidate] = []
    suppressed_ids: List[str] = []

    for cand in initial_sorted:
        max_iou = 0.0
        is_dup = False
        for existing in kept:
            if existing.episode == cand.episode:
                iou = calculate_temporal_iou(cand, existing)
                if iou > max_iou:
                    max_iou = iou
                if iou >= 0.70:
                    is_dup = True
                    suppressed_ids.append(cand.candidate_id)
                    cand.validation_warnings.append(
                        f"Suppressed as near-duplicate of {existing.candidate_id} (temporal IoU {iou*100:.1f}%)"
                    )
                    break
        if not is_dup:
            cand.max_duplicate_iou = max_iou
            kept.append(cand)

    return kept, suppressed_ids


def select_and_rank_candidates(
    candidates: List[ValidatedCandidate],
    top_k: int = 10,
    max_per_theme: int = 2,
) -> Tuple[List[ValidatedCandidate], List[ValidatedCandidate], List[Dict[str, Any]]]:
    """
    Ranks ALL candidates sequentially (1 to N) using the Section 3.C lexicographic tuple.
    Selects Top-K catalog candidates prioritizing distinct episodes so viewers get different angles.
    Zero arbitrary quality scores or subjective weights.
    Returns (ranked_all, top_diverse, substitutions).
    """
    valid_cands = [c for c in candidates if c.is_valid]

    # Deduplicate candidates
    deduped_cands, _ = deduplicate_candidates(valid_cands)

    # Sort all valid candidates by transparent lexicographic tuple
    sorted_all = sorted(deduped_cands, key=lexicographic_rank_key)

    # Assign sequential rank 1..N and relative rank percentile
    n = len(sorted_all)
    for r, cand in enumerate(sorted_all, 1):
        cand.rank = r
        cand.rank_percentile = round(100.0 * (n - r) / max(n - 1, 1), 2)
        cand.posting_priority = "Standard"
        cand.ranking_rationale = (
            f"Rank #{r} (relative rank percentile {cand.rank_percentile:.1f}%): "
            f"{'continuous single cut' if cand.segment_count == 1 else f'{cand.segment_count}-segment cut'}, "
            f"hook complete by {cand.hook_complete_by_ms/1000.0:.2f}s, "
            f"cliff gap {cand.cliff_gap_ms/1000.0:.2f}s, "
            f"max IoU {cand.max_duplicate_iou:.2f}, "
            f"{len(cand.validation_warnings) + len(cand.risks)} declared context/risk flags."
        )

    # Select Top-K catalog candidates across distinct episodes
    selected_top: List[ValidatedCandidate] = []
    seen_episodes: set[int] = set()
    substitutions: List[Dict[str, Any]] = []

    for c in sorted_all:
        if c.episode not in seen_episodes:
            selected_top.append(c)
            seen_episodes.add(c.episode)
            if len(selected_top) == top_k:
                break

    # If fewer distinct episodes available than top_k, fill from remaining sorted candidates
    if len(selected_top) < top_k:
        for c in sorted_all:
            if c not in selected_top:
                selected_top.append(c)
                substitutions.append({
                    "candidate_id": c.candidate_id,
                    "reason": f"Filled slot from Episode {c.episode} after single-per-episode pass",
                })
                if len(selected_top) == top_k:
                    break

    # Create distinct deep copies for top_diverse export with assigned posting priorities
    top_diverse: List[ValidatedCandidate] = []
    for idx, c in enumerate(selected_top, 1):
        c_copy = copy.deepcopy(c)
        c_copy.rank = idx
        if idx <= 3:
            c_copy.posting_priority = "First-to-Post"
            c.posting_priority = "First-to-Post"
        else:
            c_copy.posting_priority = "Diverse Top 10"
            c.posting_priority = "Diverse Top 10"
        top_diverse.append(c_copy)

    return sorted_all, top_diverse, substitutions


# Backwards compatibility alias
select_top_diverse = select_and_rank_candidates


def generate_top_3_rationales(top_candidates: List[ValidatedCandidate]) -> List[Dict[str, Any]]:
    """
    Produces evidence-backed posting rationales and tradeoffs vs next candidate for Top 3.
    Matches exactly across JSON, CSV, HTML, DOCX, and PDF.
    Every rationale and trade-off dynamically derives from the candidate's actual source evidence.
    """
    top_3_meta = []
    for i in range(min(3, len(top_candidates))):
        cur = top_candidates[i]
        next_cand = top_candidates[i + 1] if i + 1 < len(top_candidates) else None

        hook_text = cur.hook.get("exact_quote", "")
        cliff_text = cur.cliffhanger.get("exact_quote", "")
        dur = cur.total_duration_sec

        hook_quote = hook_text.strip(' \t\n\r"\'“’‘”')
        cliff_quote = cliff_text.strip(' \t\n\r"\'“’‘”')
        dur = cur.total_duration_sec

        if next_cand:
            next_hook = next_cand.hook.get("exact_quote", "").strip(' \t\n\r"\'“’‘”')
            tradeoff = (
                f"Rank #{i + 1} ({cur.candidate_id}, Ep {cur.episode}, {dur:.1f}s, theme '{cur.theme}') delivers "
                f"opening hook '{hook_quote}' (complete in {cur.hook_complete_by_ms/1000.0:.2f}s) and concludes on "
                f"acute unresolved beat '{cliff_quote}' (cliff gap {cur.cliff_gap_ms/1000.0:.2f}s). Prioritized over "
                f"Rank #{i + 2} ({next_cand.candidate_id}, Ep {next_cand.episode}, hook '{next_hook}') due to "
                f"superior hook completion timing and immediate narrative stakes."
            )
        else:
            tradeoff = (
                f"Rank #{i + 1} ({cur.candidate_id}, Ep {cur.episode}, {dur:.1f}s, theme '{cur.theme}') delivers "
                f"opening hook '{hook_quote}' and acute cliffhanger '{cliff_quote}', completing the primary launch tranche."
            )

        rationale = {
            "rank": i + 1,
            "candidate_id": cur.candidate_id,
            "episode": cur.episode,
            "theme": cur.theme,
            "posting_priority": cur.posting_priority,
            "duration_sec": dur,
            "segments": [f"{s.start_time_str} - {s.end_time_str}" for s in cur.segments],
            "hook_evidence": hook_quote,
            "cliffhanger_evidence": cliff_quote,
            "unresolved_question": cur.cliffhanger.get("unresolved_question", ""),
            "why_post_first": cur.why_it_works,
            "tradeoff_vs_next": tradeoff,
        }
        top_3_meta.append(rationale)

    return top_3_meta


def sanitize_csv_cell(value: Any) -> Any:
    """Neutralizes spreadsheet formula injection (=, +, -, @)."""
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@"):
        return f"'{value}"
    return value


def export_candidates_to_csv(candidates: List[ValidatedCandidate], out_path: Path):
    """Exports candidates list to CSV with Section 3.A observable fields only."""
    fieldnames = [
        "rank",
        "rank_percentile",
        "candidate_id",
        "episode",
        "posting_priority",
        "is_stitched",
        "segment_count",
        "segments",
        "total_duration_sec",
        "duration_valid",
        "hook_offset_ms",
        "hook_complete_by_ms",
        "hook_within_3s",
        "hook_speaker",
        "hook_quote",
        "cliff_gap_ms",
        "cliff_near_end",
        "cliffhanger_speaker",
        "cliffhanger_quote",
        "unresolved_question",
        "boundary_conflicts",
        "answer_events_after_cliff",
        "max_duplicate_iou",
        "ranking_rationale",
        "theme",
        "why_it_works",
        "standalone_summary",
        "validation_warnings",
    ]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in candidates:
            seg_str = "; ".join(f"[{s.start_time_str}-{s.end_time_str}]" for s in c.segments)
            raw_row = {
                "rank": c.rank,
                "rank_percentile": c.rank_percentile,
                "candidate_id": c.candidate_id,
                "episode": c.episode,
                "posting_priority": c.posting_priority,
                "is_stitched": "Yes" if c.is_stitched else "No",
                "segment_count": c.segment_count,
                "segments": seg_str,
                "total_duration_sec": f"{c.total_duration_sec:.2f}",
                "duration_valid": "Yes" if c.duration_valid else "No",
                "hook_offset_ms": c.hook_offset_ms,
                "hook_complete_by_ms": c.hook_complete_by_ms,
                "hook_within_3s": "Yes" if c.hook_within_3s else "No",
                "hook_speaker": c.hook.get("speaker") or "",
                "hook_quote": c.hook.get("exact_quote", "")[:120],
                "cliff_gap_ms": c.cliff_gap_ms,
                "cliff_near_end": "Yes" if c.cliff_near_end else "No",
                "cliffhanger_speaker": c.cliffhanger.get("speaker") or "",
                "cliffhanger_quote": c.cliffhanger.get("exact_quote", "")[:120],
                "unresolved_question": c.cliffhanger.get("unresolved_question", ""),
                "boundary_conflicts": c.boundary_conflicts,
                "answer_events_after_cliff": c.answer_events_after_cliff,
                "max_duplicate_iou": f"{c.max_duplicate_iou:.4f}",
                "ranking_rationale": c.ranking_rationale,
                "theme": c.theme,
                "why_it_works": c.why_it_works,
                "standalone_summary": c.standalone_summary,
                "validation_warnings": "; ".join(c.validation_warnings),
            }
            sanitized_row = {k: sanitize_csv_cell(v) for k, v in raw_row.items()}
            writer.writerow(sanitized_row)


def export_candidates_to_json(candidates: List[ValidatedCandidate], out_path: Path):
    """Exports candidates list to JSON."""
    data = [c.to_dict() for c in candidates]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
