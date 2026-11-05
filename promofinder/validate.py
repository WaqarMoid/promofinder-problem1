"""
Validation and boundary verification for candidate promos.
Conforms strictly to project specifications
and project specifications
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
import re

from promofinder.models import (
    Event,
    EpisodeManifest,
    CandidateDraft,
    ValidatedCandidate,
    ResolvedSegment,
    ms_to_time_str,
)


def check_dialogue_boundary_conflict(
    boundary_ms: int,
    events: List[Event],
    is_start: bool
) -> Tuple[bool, Optional[str]]:
    """
    Checks if a timestamp boundary falls strictly inside any dialogue event.
    Returns (has_conflict, description).
    Strictly inside means start_ms < boundary < end_ms.
    """
    for ev in events:
        if ev.kind == "dialogue":
            if ev.start_ms < boundary_ms < ev.end_ms:
                pos = "start" if is_start else "end"
                return True, (
                    f"Cut {pos} boundary ({ms_to_time_str(boundary_ms)}) strictly inside "
                    f"dialogue event {ev.event_id} ({ev.speaker_raw or 'Unknown'}: "
                    f"'{ev.text[:30]}...')"
                )
    return False, None


def validate_candidate_draft(
    draft: CandidateDraft,
    manifest: EpisodeManifest,
    run_id: str,
    all_manifests_map: Optional[Dict[int, EpisodeManifest]] = None,
) -> ValidatedCandidate:
    """
    Strictly validates a CandidateDraft against source events and Section 3.A observable measurements.
    Enforces duration [20.0s, 60.0s], dialogue boundary integrity,
    hook offset in [0, 3.0s], cliffhanger terminal placement, and zero answering events after cliff.
    """
    if all_manifests_map is None:
        all_manifests_map = {manifest.episode: manifest}

    errors: List[str] = []
    warnings: List[str] = []
    resolved_segments: List[ResolvedSegment] = []
    total_duration_ms = 0
    source_events_present = True
    boundary_conflicts = 0

    # 1. Validate segments count
    if not draft.segments:
        errors.append("No segments provided in candidate draft.")
        source_events_present = False
    elif len(draft.segments) > 3:
        errors.append(f"Exceeds maximum of 3 segments (got {len(draft.segments)}).")

    is_stitched = len(draft.segments) > 1
    prev_seg_end_time = -1
    prev_seg_ep = -1

    for seg_idx, seg in enumerate(draft.segments):
        target_manifest = all_manifests_map.get(seg.episode)
        if not target_manifest:
            errors.append(f"Segment {seg_idx+1} references unknown episode {seg.episode}.")
            source_events_present = False
            continue

        events_dict = {ev.event_id: ev for ev in target_manifest.events}
        if seg.start_event_id not in events_dict:
            errors.append(f"Segment {seg_idx+1} start_event_id '{seg.start_event_id}' not found in episode {seg.episode}.")
            source_events_present = False
            continue
        if seg.end_event_id not in events_dict:
            errors.append(f"Segment {seg_idx+1} end_event_id '{seg.end_event_id}' not found in episode {seg.episode}.")
            source_events_present = False
            continue

        start_ev = events_dict[seg.start_event_id]
        end_ev = events_dict[seg.end_event_id]

        # Chronological order within segment
        if start_ev.start_ms > end_ev.end_ms or (start_ev.start_ms == end_ev.end_ms and start_ev.source_order > end_ev.source_order):
            errors.append(
                f"Segment {seg_idx+1}: start_event {start_ev.event_id} occurs after end_event {end_ev.event_id}."
            )
            continue

        seg_start_ms = start_ev.start_ms
        seg_end_ms = end_ev.end_ms
        seg_duration_ms = seg_end_ms - seg_start_ms

        if seg_duration_ms <= 0:
            errors.append(
                f"Segment {seg_idx+1}: duration is non-positive ({seg_duration_ms} ms)."
            )

        # Check chronological segments order
        if is_stitched:
            if seg.episode < prev_seg_ep:
                errors.append(f"Segment {seg_idx+1} episode {seg.episode} is before previous episode {prev_seg_ep}.")
            elif seg.episode == prev_seg_ep and seg_start_ms < prev_seg_end_time:
                errors.append(f"Segment {seg_idx+1} overlaps or regresses with preceding segment.")

        prev_seg_ep = seg.episode
        prev_seg_end_time = seg_end_ms

        # Check dialogue boundary conflicts
        has_start_conflict, desc_start = check_dialogue_boundary_conflict(
            seg_start_ms, target_manifest.events, is_start=True
        )
        if has_start_conflict and desc_start:
            boundary_conflicts += 1
            errors.append(desc_start)

        has_end_conflict, desc_end = check_dialogue_boundary_conflict(
            seg_end_ms, target_manifest.events, is_start=False
        )
        if has_end_conflict and desc_end:
            boundary_conflicts += 1
            errors.append(desc_end)

        # Collect events strictly included in [seg_start_ms, seg_end_ms]
        included_events = [
            ev.event_id for ev in target_manifest.events
            if ev.start_ms >= seg_start_ms and ev.end_ms <= seg_end_ms
        ]

        # Collect ALL events that overlap [seg_start_ms, seg_end_ms]
        overlapping_events = [
            ev.event_id for ev in target_manifest.events
            if ev.start_ms < seg_end_ms and ev.end_ms > seg_start_ms
        ]

        # Check for sentence continuation at segment opening
        if start_ev.kind == "dialogue":
            t_strip = start_ev.text.strip()
            if t_strip.startswith("...") or t_strip.startswith("…"):
                warnings.append("opening_sentence_continuation: cut opens on mid-sentence continuation without prior clause.")

        resolved_segments.append(
            ResolvedSegment(
                episode=seg.episode,
                start_event_id=seg.start_event_id,
                end_event_id=seg.end_event_id,
                start_ms=seg_start_ms,
                end_ms=seg_end_ms,
                start_time_str=ms_to_time_str(seg_start_ms),
                end_time_str=ms_to_time_str(seg_end_ms),
                duration_ms=seg_duration_ms,
                duration_sec=seg_duration_ms / 1000.0,
                event_ids=included_events,
                overlapping_event_ids=overlapping_events,
                source_line_start=start_ev.source_line_start,
                source_line_end=end_ev.source_line_end,
            )
        )
        total_duration_ms += seg_duration_ms

    total_duration_sec = total_duration_ms / 1000.0
    duration_valid = (20000 <= total_duration_ms <= 60000)

    # 2. Check total duration bounds (20.0s to 60.0s)
    if not duration_valid:
        if total_duration_sec < 20.0:
            errors.append(f"Total duration {total_duration_sec:.2f}s is below 20.0s minimum.")
        else:
            errors.append(f"Total duration {total_duration_sec:.2f}s exceeds 60.0s maximum.")

    first_seg_start = resolved_segments[0].start_ms if resolved_segments else 0
    last_seg_end = resolved_segments[-1].end_ms if resolved_segments else 0

    # 3. Validate Hook
    hook_data: Dict[str, Any] = dict(draft.hook)
    hook_ev_id = draft.hook.get("event_id")
    events_map = {ev.event_id: ev for ev in manifest.events}
    hook_offset_ms = 0
    hook_complete_by_ms = 0
    hook_within_3s = False
    hook_ev: Optional[Event] = None

    if not hook_ev_id or hook_ev_id not in events_map:
        errors.append(f"Hook event ID '{hook_ev_id}' not found in episode events.")
        source_events_present = False
    else:
        hook_ev = events_map[hook_ev_id]
        hook_offset_ms = hook_ev.start_ms - first_seg_start
        hook_complete_by_ms = hook_ev.end_ms - first_seg_start
        hook_within_3s = (0 <= hook_complete_by_ms <= 3000)

        hook_offset_sec = hook_offset_ms / 1000.0
        hook_data["offset_sec"] = round(hook_offset_sec, 2)
        hook_data["exact_quote"] = hook_ev.text
        hook_data["speaker"] = hook_ev.speaker_raw

        # Check if hook event is within the clip bounds
        if hook_ev.start_ms < first_seg_start or hook_ev.end_ms > last_seg_end:
            errors.append(f"Hook event {hook_ev_id} is outside the selected footage boundary.")
            source_events_present = False

        if hook_offset_ms < 0 or hook_offset_ms > 3000:
            errors.append(
                f"Hook offset ({hook_offset_sec:.2f}s) is outside the mandatory 0-3.0s window."
            )

        # Hook completion check (Hard Eligibility Gate per Section 3.2)
        hook_data["is_first_3s_complete"] = hook_within_3s
        if not hook_within_3s:
            errors.append(
                f"Hook event {hook_ev_id} completion ({hook_complete_by_ms/1000.0:.2f}s) "
                f"exceeds the mandatory <=3.00s completion threshold (0 <= hook_complete_by_ms <= 3000)."
            )

    # 4. Validate Cliffhanger
    cliff_data: Dict[str, Any] = dict(draft.cliffhanger)
    cliff_ev_id = draft.cliffhanger.get("event_id")
    cliff_gap_ms = 0
    cliff_near_end = False
    cliff_ev: Optional[Event] = None

    if not cliff_ev_id or cliff_ev_id not in events_map:
        errors.append(f"Cliffhanger event ID '{cliff_ev_id}' not found in episode events.")
        source_events_present = False
    else:
        cliff_ev = events_map[cliff_ev_id]
        cliff_gap_ms = last_seg_end - cliff_ev.end_ms
        cliff_near_end = (0 <= cliff_gap_ms <= 3000)
        cliff_data["exact_quote"] = cliff_ev.text
        cliff_data["speaker"] = cliff_ev.speaker_raw

        # Check if cliffhanger is strictly within selected footage
        if cliff_ev.start_ms < first_seg_start or cliff_ev.end_ms > last_seg_end:
            errors.append(
                f"Cliffhanger event {cliff_ev_id} ({cliff_ev.start_str}-{cliff_ev.end_str}) "
                f"is outside the selected footage [{ms_to_time_str(first_seg_start)}-{ms_to_time_str(last_seg_end)}]."
            )
            source_events_present = False

        # Cliffhanger beat must terminate at or within 3s of the cut end
        if cliff_gap_ms < 0:
            errors.append("Cliffhanger event ends after cut boundary.")
        elif not cliff_near_end:
            errors.append(
                f"Cliffhanger event ends {cliff_gap_ms/1000.0:.1f}s before cut end; "
                f"terminal cut must land on or immediately following the cliffhanger beat."
            )

    # 5. Check answering events after cliff inside clip
    answer_events_after_cliff = 0
    if cliff_ev:
        dialogue_after = [
            ev for ev in manifest.events
            if ev.kind == "dialogue"
            and ev.event_id != cliff_ev.event_id
            and ev.start_ms >= cliff_ev.end_ms
            and ev.end_ms <= last_seg_end
        ]
        answer_events_after_cliff = len(dialogue_after)
        if answer_events_after_cliff > 0:
            errors.append(
                f"Answer events after cliff: {answer_events_after_cliff} dialogue beat(s) "
                f"occur after cliffhanger beat inside footage, defusing the unresolved question."
            )

    # Mechanical eligibility per Section 3.2
    is_valid = (
        duration_valid
        and source_events_present
        and boundary_conflicts == 0
        and (0 <= hook_offset_ms <= 3000)
        and hook_within_3s
        and cliff_near_end
        and answer_events_after_cliff == 0
        and len(errors) == 0
    )
    candidate_id = f"{run_id}-E{manifest.episode:03d}-{draft.local_id}"

    return ValidatedCandidate(
        candidate_id=candidate_id,
        run_id=run_id,
        episode=manifest.episode,
        is_stitched=is_stitched,
        segments=resolved_segments,
        total_duration_ms=total_duration_ms,
        total_duration_sec=total_duration_sec,
        duration_valid=duration_valid,
        hook=hook_data,
        hook_offset_ms=hook_offset_ms,
        hook_complete_by_ms=hook_complete_by_ms,
        hook_within_3s=hook_within_3s,
        cliffhanger=cliff_data,
        cliff_gap_ms=cliff_gap_ms,
        cliff_near_end=cliff_near_end,
        boundary_conflicts=boundary_conflicts,
        answer_events_after_cliff=answer_events_after_cliff,
        segment_count=len(resolved_segments),
        max_duplicate_iou=0.0,
        source_events_present=source_events_present,
        why_it_works=draft.why_it_works,
        theme=draft.theme,
        standalone_summary=draft.standalone_summary or "",
        is_valid=is_valid,
        validation_errors=errors,
        validation_warnings=warnings,
        risks=draft.risks or [],
        join_reason=draft.join_reason,
    )
