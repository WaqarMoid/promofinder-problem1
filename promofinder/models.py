"""
Data contracts and models for promofinder.
Conforms strictly to project specifications
and project specifications
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import json


def ms_to_time_str(ms: int) -> str:
    """Converts milliseconds to MM:SS.xx or HH:MM:SS.xx string format."""
    total_seconds = ms / 1000.0
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"
    return f"{minutes:02d}:{seconds:05.2f}"


def parse_time_str_to_ms(time_str: str) -> int:
    """
    Parses 'MM:SS.xx' or 'HH:MM:SS.xx' into milliseconds.
    Raises ValueError on invalid formats or seconds >= 60.
    """
    s = time_str.strip()
    parts = s.split(":")
    if len(parts) == 2:
        minutes = int(parts[0])
        seconds = float(parts[1])
        if seconds >= 60.0 or seconds < 0:
            raise ValueError(f"Invalid seconds value in timestamp: {time_str}")
        return int(round((minutes * 60 + seconds) * 1000))
    elif len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        if minutes >= 60 or seconds >= 60.0 or seconds < 0:
            raise ValueError(f"Invalid time components in timestamp: {time_str}")
        return int(round((hours * 3600 + minutes * 60 + seconds) * 1000))
    else:
        raise ValueError(f"Unsupported timestamp format: '{time_str}'")


@dataclass
class Event:
    event_id: str                      # e.g. "E001-B0001"
    episode: int                       # 1..50
    scene_id: str                      # "SCENE 01"
    kind: str                          # "camera", "action", "sound", "dialogue"
    speaker_raw: Optional[str]         # speaker name and notes if dialogue
    speaker_name: Optional[str]        # cleaned speaker name
    start_ms: int                      # parsed start time in ms
    end_ms: int                        # parsed end time in ms
    start_str: str                     # original string, e.g. "00:00.00"
    end_str: str                       # original string, e.g. "00:04.80"
    text: str                          # body text
    source_file: str                   # filename
    source_line_start: int             # line start (1-based)
    source_line_end: int               # line end (1-based)
    source_order: int                  # 1-based sequential index in file

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def duration_sec(self) -> float:
        return (self.end_ms - self.start_ms) / 1000.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Scene:
    scene_id: str
    heading: str
    start_ms: int
    end_ms: int
    start_str: str
    end_str: str
    source_line: int


@dataclass
class EpisodeManifest:
    episode: int
    file_path: str
    file_name: str
    sha256: str
    bytes_count: int
    line_count: int
    logline: str
    continuity: str
    scenes: List[Scene] = field(default_factory=list)
    events: List[Event] = field(default_factory=list)
    duration_ms: int = 0
    start_regressions: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def timeline_events(self) -> List[Event]:
        """Returns events sorted chronologically by (start_ms, source_order) for temporal windowing."""
        return sorted(self.events, key=lambda ev: (ev.start_ms, ev.source_order))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode": self.episode,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "sha256": self.sha256,
            "bytes_count": self.bytes_count,
            "line_count": self.line_count,
            "logline": self.logline,
            "continuity": self.continuity,
            "event_count": len(self.events),
            "scene_count": len(self.scenes),
            "duration_ms": self.duration_ms,
            "duration_formatted": ms_to_time_str(self.duration_ms),
            "start_regressions_count": len(self.start_regressions),
            "start_regressions": self.start_regressions,
            "warnings": self.warnings,
        }


@dataclass
class SegmentDraft:
    episode: int
    start_event_id: str
    end_event_id: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateDraft:
    local_id: str
    segments: List[SegmentDraft]
    hook: Dict[str, str]           # {"event_id": str, "description": str}
    cliffhanger: Dict[str, str]    # {"event_id": str, "unresolved_question": str}
    why_it_works: str
    theme: str
    standalone_summary: Optional[str] = None
    risks: List[str] = field(default_factory=list)
    join_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "local_id": self.local_id,
            "segments": [s.to_dict() for s in self.segments],
            "hook": self.hook,
            "cliffhanger": self.cliffhanger,
            "why_it_works": self.why_it_works,
            "theme": self.theme,
            "standalone_summary": self.standalone_summary,
            "risks": self.risks,
            "join_reason": self.join_reason,
        }


@dataclass
class ResolvedSegment:
    episode: int
    start_event_id: str
    end_event_id: str
    start_ms: int
    end_ms: int
    start_time_str: str
    end_time_str: str
    duration_ms: int
    duration_sec: float
    event_ids: List[str]
    overlapping_event_ids: List[str] = field(default_factory=list)
    source_line_start: int = 0
    source_line_end: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidatedCandidate:
    candidate_id: str              # e.g. "RUN-E001-C1"
    run_id: str
    episode: int
    is_stitched: bool
    segments: List[ResolvedSegment]
    total_duration_ms: int
    total_duration_sec: float
    duration_valid: bool
    hook: Dict[str, Any]           # event_id, description, exact_quote, speaker, offset_sec, is_first_3s_complete
    hook_offset_ms: int
    hook_complete_by_ms: int
    hook_within_3s: bool
    cliffhanger: Dict[str, Any]    # event_id, unresolved_question, exact_quote, speaker
    cliff_gap_ms: int
    cliff_near_end: bool
    boundary_conflicts: int
    answer_events_after_cliff: int
    segment_count: int
    max_duplicate_iou: float = 0.0
    source_events_present: bool = True
    why_it_works: str = ""
    theme: str = ""
    rank: int = 0                  # 1 to N sequential
    rank_percentile: Optional[float] = None
    ranking_rationale: str = ""
    posting_priority: str = "Standard"  # "First-to-Post", "Diverse Top 10", "Standard"
    standalone_summary: str = ""
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    join_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "run_id": self.run_id,
            "episode": self.episode,
            "is_stitched": self.is_stitched,
            "segments": [s.to_dict() for s in self.segments],
            "total_duration_ms": self.total_duration_ms,
            "total_duration_sec": round(self.total_duration_sec, 2),
            "duration_valid": self.duration_valid,
            "hook": self.hook,
            "hook_offset_ms": self.hook_offset_ms,
            "hook_complete_by_ms": self.hook_complete_by_ms,
            "hook_within_3s": self.hook_within_3s,
            "cliffhanger": self.cliffhanger,
            "cliff_gap_ms": self.cliff_gap_ms,
            "cliff_near_end": self.cliff_near_end,
            "boundary_conflicts": self.boundary_conflicts,
            "answer_events_after_cliff": self.answer_events_after_cliff,
            "segment_count": self.segment_count,
            "max_duplicate_iou": round(self.max_duplicate_iou, 4),
            "source_events_present": self.source_events_present,
            "why_it_works": self.why_it_works,
            "theme": self.theme,
            "rank": self.rank,
            "rank_percentile": self.rank_percentile,
            "ranking_rationale": self.ranking_rationale,
            "posting_priority": self.posting_priority,
            "standalone_summary": self.standalone_summary,
            "is_valid": self.is_valid,
            "validation_errors": self.validation_errors,
            "validation_warnings": self.validation_warnings,
            "risks": self.risks,
            "join_reason": self.join_reason,
        }


@dataclass
class EpisodeAnalysis:
    episode: int
    status: str                    # "success", "no_candidate", "pending", "failed"
    reason: Optional[str]
    summary: str                   # <=80 words
    candidates: List[CandidateDraft]
    request_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode": self.episode,
            "status": self.status,
            "reason": self.reason,
            "summary": self.summary,
            "candidates": [c.to_dict() for c in self.candidates],
            "request_id": self.request_id,
        }
