"""
Reconciliation Gate Tests for promofinder Problem 1 Prototype.
Tests behavioral invariants, status arithmetic, observable measurement formulas,
zero subjective scores, and cross-file agreement without hardcoding preferred winners in correctness tests.
"""

import os
import json
import csv
import unittest
from pathlib import Path

from promofinder.parser import parse_all_episodes
from promofinder.provider import DeterministicBaselineProvider, ManualProvider
from promofinder.validate import validate_candidate_draft
from promofinder.models import CandidateDraft, SegmentDraft, Event, EpisodeManifest


class TestReconciliationGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scripts_dir = Path(os.environ.get("PROMOFINDER_SCREENPLAYS_DIR", "screenplays"))
        cls.has_scripts = cls.scripts_dir.exists() and len(list(cls.scripts_dir.glob("episode-*.txt"))) > 0
        if cls.has_scripts:
            cls.manifests = parse_all_episodes(cls.scripts_dir)
            cls.provider = DeterministicBaselineProvider()
            cls.analyses = [cls.provider.generate_analysis(m) for m in cls.manifests]

    def test_status_arithmetic_and_100_percent_coverage(self):
        """Dynamic status counts must account for all episodes: success + no_candidate + pending + failed == total."""
        if not self.has_scripts:
            self.skipTest("Screenplay files not available for full reconciliation.")

        status_counts = {}
        for a in self.analyses:
            status_counts[a.status] = status_counts.get(a.status, 0) + 1

        success = status_counts.get("success", 0)
        no_candidate = status_counts.get("no_candidate", 0)
        pending = status_counts.get("pending", 0)
        failed = status_counts.get("failed", 0)

        total = len(self.manifests)
        self.assertEqual(success + no_candidate + pending + failed, total)
        self.assertEqual(pending, 0)
        self.assertEqual(failed, 0)

        # Processing coverage arithmetic: (success + no_candidate) / total == 100.0%
        processing_coverage = (success + no_candidate) / total * 100.0
        self.assertEqual(processing_coverage, 100.0)

    def test_missing_response_handled_as_pending(self):
        """Manual provider with missing response file returns status='pending' with reason."""
        tmp_req = Path("tmp/test_gates_requests")
        tmp_resp = Path("tmp/test_gates_responses")
        tmp_req.mkdir(parents=True, exist_ok=True)
        tmp_resp.mkdir(parents=True, exist_ok=True)

        manual_p = ManualProvider(requests_dir=tmp_req, responses_dir=tmp_resp)
        sample_manifest = getattr(self, "manifests", [None])[0] if self.has_scripts else None
        if not sample_manifest:
            # Fall back to sample_input if available
            sample_dir = Path("sample_input")
            if sample_dir.exists():
                s_manifests = parse_all_episodes(sample_dir)
                if s_manifests:
                    sample_manifest = s_manifests[0]

        if not sample_manifest:
            self.skipTest("Need at least one manifest.")

        analysis = manual_p.generate_analysis(sample_manifest)
        self.assertEqual(analysis.status, "pending")
        self.assertIn("Awaiting manual response", analysis.reason or "")
        self.assertEqual(len(analysis.candidates), 0)

    def test_mechanical_eligibility_observable_fields(self):
        """Verifies that all candidates contain Section 3.A observable fields and zero subjective score fields."""
        if not self.has_scripts:
            self.skipTest("Screenplay files not available.")

        manifest_map = {m.episode: m for m in self.manifests}
        candidates_checked = 0

        for a in self.analyses:
            m = manifest_map[a.episode]
            for draft in a.candidates:
                val = validate_candidate_draft(draft, m, "test", manifest_map)
                candidates_checked += 1

                # Check observable fields are present
                self.assertIsInstance(val.duration_valid, bool)
                self.assertIsInstance(val.hook_offset_ms, int)
                self.assertIsInstance(val.hook_complete_by_ms, int)
                self.assertIsInstance(val.hook_within_3s, bool)
                self.assertIsInstance(val.cliff_gap_ms, int)
                self.assertIsInstance(val.zero_speech_bisection, bool)
                self.assertIsInstance(val.single_episode_continuous, bool)
                self.assertIsInstance(val.is_valid, bool)

                # Strict hook completion invariant on valid candidates
                if val.is_valid:
                    self.assertTrue(val.hook_within_3s)
                    self.assertLessEqual(val.hook_complete_by_ms, 3000)
                    self.assertGreaterEqual(val.hook_complete_by_ms, 0)

                # Strictly assert zero subjective human-assigned rating or score fields exist
                cand_dict = val.to_dict()
                self.assertNotIn("scores", cand_dict)
                self.assertNotIn("composite_score", cand_dict)
                self.assertNotIn("human_rating", cand_dict)
                self.assertNotIn("human_approved", cand_dict)
                self.assertNotIn("narrative_score", cand_dict)
                self.assertNotIn("virality_score", cand_dict)

        self.assertGreater(candidates_checked, 0)

    def test_rejection_when_answer_event_occurs_inside_clip(self):
        """Verifies rejection when a dialogue beat answering the question occurs after cliff inside the cut."""
        ev_start = Event(
            event_id="E902-B0001", episode=902, scene_id="SCENE 01", kind="action",
            speaker_raw=None, speaker_name=None, start_ms=0, end_ms=2000,
            start_str="00:00.00", end_str="00:02.00", text="Intro",
            source_file="f.txt", source_line_start=1, source_line_end=2, source_order=1
        )
        ev_hook = Event(
            event_id="E902-B0002", episode=902, scene_id="SCENE 01", kind="dialogue",
            speaker_raw="A", speaker_name="A", start_ms=2000, end_ms=4000,
            start_str="00:02.00", end_str="00:04.00", text="Opening hook",
            source_file="f.txt", source_line_start=3, source_line_end=4, source_order=2
        )
        ev_cliff = Event(
            event_id="E902-B0003", episode=902, scene_id="SCENE 01", kind="dialogue",
            speaker_raw="A", speaker_name="A", start_ms=25000, end_ms=28000,
            start_str="00:25.00", end_str="00:28.00", text="Is it true?",
            source_file="f.txt", source_line_start=5, source_line_end=6, source_order=3
        )
        ev_answer = Event(
            event_id="E902-B0004", episode=902, scene_id="SCENE 01", kind="dialogue",
            speaker_raw="B", speaker_name="B", start_ms=28500, end_ms=30000,
            start_str="00:28.50", end_str="00:30.00", text="Yes, it is.",
            source_file="f.txt", source_line_start=7, source_line_end=8, source_order=4
        )

        manifest = EpisodeManifest(
            episode=902, file_path="f.txt", file_name="f.txt", sha256="abc",
            bytes_count=100, line_count=10, logline="log", continuity="cont",
            events=[ev_start, ev_hook, ev_cliff, ev_answer]
        )

        # Draft includes ev_answer after cliff: must be rejected
        draft_with_answer = CandidateDraft(
            local_id="C_ANS",
            segments=[SegmentDraft(episode=902, start_event_id="E902-B0001", end_event_id="E902-B0004")],
            hook={"event_id": "E902-B0002", "description": "h"},
            cliffhanger={"event_id": "E902-B0003", "unresolved_question": "Is it true?"},
            why_it_works="w", theme="t"
        )
        val = validate_candidate_draft(draft_with_answer, manifest, "test")
        self.assertFalse(val.is_valid)
        self.assertGreater(val.answer_events_after_cliff, 0)
        self.assertTrue(any("Answer events after cliff" in e for e in val.validation_errors))

    def test_canonical_run_deliverables_consistency_if_present(self):
        """If a canonical run directory exists, verify zero human rating fields, exact run_facts agreement, 100% coverage, and hook completion <= 3s."""
        run_dir = Path(os.environ.get("PROMOFINDER_CANONICAL_RUN", "runs/canonical"))
        if not run_dir.exists():
            return  # Canonical run not present in environment

        facts_file = run_dir / "run_facts.json"
        self.assertTrue(facts_file.exists())
        with open(facts_file, "r", encoding="utf-8") as f:
            facts = json.load(f)

        self.assertEqual(facts["coverage_and_yield"]["processing_coverage_pct"], 100.0)
        self.assertEqual(facts["model_execution_disclosure"]["known_paid_api_cost_usd"], 0.00)
        self.assertEqual(facts["model_execution_disclosure"]["external_model_calls"], 0)

        # Verify no subjective scores in top promos and hook completion <= 3000ms
        for p in facts["top_promos"]:
            self.assertNotIn("scores", p)
            self.assertNotIn("composite_score", p)
            self.assertIn("hook_complete_by_ms", p)
            self.assertLessEqual(p["hook_complete_by_ms"], 3000)
            self.assertTrue(p["hook_within_3s"])
            self.assertIn("cliff_gap_ms", p)


if __name__ == "__main__":
    unittest.main()
