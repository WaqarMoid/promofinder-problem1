"""
Parser module for Screenplay ingestion.
Conforms strictly to project specifications
"""

from __future__ import annotations
import os
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any

from promofinder.models import (
    Event,
    Scene,
    EpisodeManifest,
    parse_time_str_to_ms,
    ms_to_time_str,
)


# Regular expressions for script parsing
RE_EPISODE_FILE = re.compile(r"episode-(\d+)", re.IGNORECASE)
RE_EPISODE_HEADER = re.compile(r"^EPISODE NUMBER:\s*(?:Episode\s*)?(\d+)", re.IGNORECASE)
RE_LOGLINE_HEADER = re.compile(r"^EPISODE LOGLINE:\s*(.*)", re.IGNORECASE)
RE_CONTINUITY_HEADER = re.compile(r"^CONTINUITY NOTES:\s*(.*)", re.IGNORECASE)

RE_SCENE_START = re.compile(r"^SCENE\s+(\d+)", re.IGNORECASE)
RE_SCENE_HEADING = re.compile(r"^Scene heading:\s*(.*)", re.IGNORECASE)
RE_SCENE_TIME_START = re.compile(r"^Scene start:\s*([0-9:.]+)", re.IGNORECASE)
RE_SCENE_TIME_END = re.compile(r"^Scene end:\s*([0-9:.]+)", re.IGNORECASE)

RE_EVENT_HEADER = re.compile(r"^\*\*(.+?)\*\*:?$")
RE_EVENT_TIME = re.compile(r"^Start:\s*\(([0-9:.]+)\)\s*\|\s*End:\s*\(([0-9:.]+)\)$")
RE_SCRIPT_START = re.compile(r"^---\s*SCRIPT\s+START\s*---", re.IGNORECASE)
RE_SCRIPT_END = re.compile(r"^---\s*SCRIPT\s+END\s*---", re.IGNORECASE)


def classify_header(header_content: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Classifies header string into (kind, speaker_raw, speaker_name).
    Kinds: 'camera', 'action', 'sound', 'dialogue'.
    """
    norm = header_content.strip()
    # Remove trailing colon if inside the bold marker
    if norm.endswith(":"):
        norm = norm[:-1].strip()

    upper = norm.upper()
    if upper == "CAMERA":
        return "camera", None, None
    elif upper in ("ACTION", "ACTIONS"):
        return "action", None, None
    elif upper in ("SOUND FX", "SOUND", "SFX"):
        return "sound", None, None
    else:
        # Dialogue event: extract speaker name and delivery note
        speaker_raw = norm
        # Extract base name before any parenthesis
        m_paren = re.match(r"^([^\(]+?)(?:\s*\((.*)\))?$", norm)
        if m_paren:
            speaker_name = m_paren.group(1).strip()
        else:
            speaker_name = norm
        return "dialogue", speaker_raw, speaker_name


def parse_screenplay_file(file_path: Path) -> EpisodeManifest:
    """
    Parses a single screenplay file into an EpisodeManifest.
    Uses strict UTF-8-sig decoding and preserves file provenance.
    """
    with open(file_path, "rb") as f:
        raw_bytes = f.read()

    file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode("utf-8-sig")
    lines = text.splitlines()

    # Extract episode number from filename
    m_ep_file = RE_EPISODE_FILE.search(file_path.name)
    ep_num_from_filename = int(m_ep_file.group(1)) if m_ep_file else -1

    logline = ""
    continuity = ""
    ep_num_from_header = None
    warnings: List[str] = []

    in_script = False
    script_start_line = -1

    # Phase 1: parse metadata before SCRIPT START
    for idx, line in enumerate(lines):
        line_clean = line.strip()
        if RE_SCRIPT_START.match(line_clean):
            in_script = True
            script_start_line = idx + 1
            break

        m_num = RE_EPISODE_HEADER.match(line_clean)
        if m_num:
            ep_num_from_header = int(m_num.group(1))
            continue

        m_log = RE_LOGLINE_HEADER.match(line_clean)
        if m_log:
            logline = m_log.group(1).strip()
            continue

        m_cont = RE_CONTINUITY_HEADER.match(line_clean)
        if m_cont:
            continuity = m_cont.group(1).strip()
            continue

    if not in_script:
        raise ValueError(f"Missing '--- SCRIPT START ---' marker in {file_path}")

    episode_num = ep_num_from_filename
    if ep_num_from_header is not None and ep_num_from_header != ep_num_from_filename:
        warnings.append(
            f"Filename episode ({ep_num_from_filename}) != header episode ({ep_num_from_header})"
        )

    # Phase 2: parse scenes and timed events
    scenes: List[Scene] = []
    events: List[Event] = []
    start_regressions: List[Dict[str, Any]] = []

    current_scene_id = "SCENE 01"
    current_scene_heading = ""
    current_scene_start_ms = 0
    current_scene_end_ms = 0
    current_scene_start_str = "00:00.00"
    current_scene_end_str = "00:00.00"
    current_scene_line = script_start_line

    idx = script_start_line
    total_lines = len(lines)
    source_order = 0
    last_event_start_ms = -1

    while idx < total_lines:
        line_raw = lines[idx]
        line = line_raw.strip()

        if RE_SCRIPT_END.match(line):
            break

        # Check for Scene start
        m_scene = RE_SCENE_START.match(line)
        if m_scene:
            scene_num = int(m_scene.group(1))
            current_scene_id = f"SCENE {scene_num:02d}"
            current_scene_line = idx + 1
            idx += 1
            # Scan scene metadata lines
            while idx < total_lines:
                s_line = lines[idx].strip()
                m_head = RE_SCENE_HEADING.match(s_line)
                if m_head:
                    current_scene_heading = m_head.group(1).strip()
                    idx += 1
                    continue
                m_tstart = RE_SCENE_TIME_START.match(s_line)
                if m_tstart:
                    current_scene_start_str = m_tstart.group(1)
                    current_scene_start_ms = parse_time_str_to_ms(current_scene_start_str)
                    idx += 1
                    continue
                m_tend = RE_SCENE_TIME_END.match(s_line)
                if m_tend:
                    current_scene_end_str = m_tend.group(1)
                    current_scene_end_ms = parse_time_str_to_ms(current_scene_end_str)
                    idx += 1
                    continue
                if s_line.startswith("**") or RE_SCENE_START.match(s_line) or RE_SCRIPT_END.match(s_line):
                    break
                idx += 1

            scenes.append(
                Scene(
                    scene_id=current_scene_id,
                    heading=current_scene_heading,
                    start_ms=current_scene_start_ms,
                    end_ms=current_scene_end_ms,
                    start_str=current_scene_start_str,
                    end_str=current_scene_end_str,
                    source_line=current_scene_line,
                )
            )
            continue

        # Check for event header
        m_head = RE_EVENT_HEADER.match(line)
        if m_head:
            header_raw = m_head.group(1)
            event_line_start = idx + 1

            # Next non-empty line must be timing
            idx += 1
            while idx < total_lines and not lines[idx].strip():
                idx += 1

            if idx >= total_lines:
                warnings.append(f"Header at line {event_line_start} has no following timestamp")
                break

            time_line = lines[idx].strip()
            m_time = RE_EVENT_TIME.match(time_line)
            if not m_time:
                warnings.append(
                    f"Line {idx+1}: Expected Start/End timestamp after header '{header_raw}', got '{time_line}'"
                )
                idx += 1
                continue

            start_str = m_time.group(1)
            end_str = m_time.group(2)
            try:
                start_ms = parse_time_str_to_ms(start_str)
                end_ms = parse_time_str_to_ms(end_str)
            except ValueError as e:
                warnings.append(f"Line {idx+1}: Timestamp parsing error: {e}")
                idx += 1
                continue

            if end_ms <= start_ms:
                warnings.append(
                    f"Line {idx+1}: Non-positive duration: start {start_str} >= end {end_str}"
                )

            # Check start regression
            if last_event_start_ms >= 0 and start_ms < last_event_start_ms:
                start_regressions.append({
                    "event_index": source_order + 1,
                    "line": event_line_start,
                    "start_ms": start_ms,
                    "prev_start_ms": last_event_start_ms,
                    "start_str": start_str,
                })
            last_event_start_ms = start_ms

            # Collect body text until next header / scene / script end
            body_lines: List[str] = []
            idx += 1
            body_start_line = idx + 1
            while idx < total_lines:
                cur = lines[idx].strip()
                if (
                    RE_EVENT_HEADER.match(cur)
                    or RE_SCENE_START.match(cur)
                    or RE_SCRIPT_END.match(cur)
                ):
                    break
                body_lines.append(lines[idx])
                idx += 1

            event_line_end = idx

            body_text = "\n".join(body_lines).strip()
            kind, speaker_raw, speaker_name = classify_header(header_raw)
            source_order += 1
            event_id = f"E{episode_num:03d}-B{source_order:04d}"

            events.append(
                Event(
                    event_id=event_id,
                    episode=episode_num,
                    scene_id=current_scene_id,
                    kind=kind,
                    speaker_raw=speaker_raw,
                    speaker_name=speaker_name,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    start_str=start_str,
                    end_str=end_str,
                    text=body_text,
                    source_file=file_path.name,
                    source_line_start=event_line_start,
                    source_line_end=event_line_end,
                    source_order=source_order,
                )
            )
            continue

        idx += 1

    episode_duration_ms = max((ev.end_ms for ev in events), default=0)

    # Discrepancy check with scene ends
    if scenes:
        max_scene_end = max(s.end_ms for s in scenes)
        if abs(max_scene_end - episode_duration_ms) > 1000:
            warnings.append(
                f"Scene end ({ms_to_time_str(max_scene_end)}) differs from max event end ({ms_to_time_str(episode_duration_ms)}) by >1s"
            )

    return EpisodeManifest(
        episode=episode_num,
        file_path=str(file_path),
        file_name=file_path.name,
        sha256=file_sha256,
        bytes_count=len(raw_bytes),
        line_count=len(lines),
        logline=logline,
        continuity=continuity,
        scenes=scenes,
        events=events,
        duration_ms=episode_duration_ms,
        start_regressions=start_regressions,
        warnings=warnings,
    )


def parse_all_episodes(input_dir: Path) -> List[EpisodeManifest]:
    """
    Discovers all screenplay .txt files recursively, sorts them by episode number,
    and parses each one strictly.
    """
    p = Path(input_dir)
    txt_files = list(p.rglob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"No .txt screenplay files found in {input_dir}")

    # Map files by episode number
    ep_files: List[Tuple[int, Path]] = []
    for f in txt_files:
        m = RE_EPISODE_FILE.search(f.name)
        if m:
            ep_num = int(m.group(1))
            ep_files.append((ep_num, f))
        else:
            raise ValueError(f"Filename does not match expected episode-NNN pattern: {f.name}")

    ep_files.sort(key=lambda x: x[0])

    # Check for missing or duplicate episodes
    seen_episodes = set()
    for ep_num, f in ep_files:
        if ep_num in seen_episodes:
            raise ValueError(f"Duplicate episode number detected: {ep_num} ({f.name})")
        seen_episodes.add(ep_num)

    manifests: List[EpisodeManifest] = []
    for ep_num, f in ep_files:
        manifest = parse_screenplay_file(f)
        manifests.append(manifest)

    return manifests
