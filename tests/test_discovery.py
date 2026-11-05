"""
Unit tests for candidate discovery, validation, and ranking.
Conforms strictly to candidate eligibility and ranking specifications.
"""

import os
import unittest
from pathlib import Path

from promofinder.parser import parse_all_episodes
from promofinder.models import CandidateDraft, SegmentDraft
from promofinder.provider import DeterministicBaselineProvider
from promofinder.validate import validate_candidate_draft
from promofinder.rank import deduplicate_candidates, select_and_rank_candidates


class TestDiscoveryAndRanking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scripts_dir = Path(os.environ.get("PROMOFINDER_SCREENPLAYS_DIR", "screenplays"))
        if not cls.scripts_dir.exists():
            raise unittest.SkipTest("Full screenplay pack is absent. Skipping full-pack discovery tests.")
        cls.manifests = parse_all_episodes(cls.scripts_dir)
        cls.manifest_map = {m.episode: m for m in cls.manifests}
        cls.provider = DeterministicBaselineProvider()

    def test_validation_rejects_duration_out_of_bounds(self):
        m1 = self.manifest_map[1]
        short_draft = CandidateDraft(
            local_id="C_SHORT",
            segments=[SegmentDraft(episode=1, start_event_id="E001-B0001", end_event_id="E001-B0002")],
            hook={"event_id": "E001-B0001", "description": "Too short"},
            cliffhanger={"event_id": "E001-B0002", "unresolved_question": "Why?"},
            why_it_works="Short test",
            theme="test",
        )
        validated = validate_candidate_draft(short_draft, m1, run_id="test", all_manifests_map=self.manifest_map)
        self.assertFalse(validated.is_valid)
        self.assertTrue(any("below 20.0s" in err for err in validated.validation_errors))

    def test_validation_rejects_hook_outside_3_seconds(self):
        m1 = self.manifest_map[1]
        late_hook_draft = CandidateDraft(
            local_id="C_LATE",
            segments=[SegmentDraft(episode=1, start_event_id="E001-B0001", end_event_id="E001-B0025")],
            hook={"event_id": "E001-B0010", "description": "Late hook"},
            cliffhanger={"event_id": "E001-B0025", "unresolved_question": "Why?"},
            why_it_works="Late hook test",
            theme="test",
        )
        validated = validate_candidate_draft(late_hook_draft, m1, run_id="test", all_manifests_map=self.manifest_map)
        self.assertFalse(validated.is_valid)
        self.assertTrue(any("outside the mandatory 0-3.0s window" in err for err in validated.validation_errors))

    def test_validation_rejects_hook_completion_after_3_seconds(self):
        m1 = self.manifest_map[1]
        # B0001 starts at 0ms and ends at 4800ms (offset 0s, complete at 4.8s > 3.0s)
        draft = CandidateDraft(
            local_id="C_LONG_HOOK",
            segments=[SegmentDraft(episode=1, start_event_id="E001-B0001", end_event_id="E001-B0025")],
            hook={"event_id": "E001-B0001", "description": "Long hook completing at 4.8s"},
            cliffhanger={"event_id": "E001-B0025", "unresolved_question": "Why?"},
            why_it_works="Test hook completion",
            theme="test",
        )
        val = validate_candidate_draft(draft, m1, run_id="test", all_manifests_map=self.manifest_map)
        self.assertFalse(val.is_valid)
        self.assertFalse(val.hook_within_3s)
        self.assertEqual(val.hook_offset_ms, 0)
        self.assertEqual(val.hook_complete_by_ms, 4800)
        self.assertTrue(any("exceeds the mandatory <=3.00s completion threshold" in err for err in val.validation_errors))

    def test_validation_rejects_cliffhanger_outside_footage(self):
        m1 = self.manifest_map[1]
        out_of_bounds_draft = CandidateDraft(
            local_id="C_OUT",
            segments=[SegmentDraft(episode=1, start_event_id="E001-B0015", end_event_id="E001-B0030")],
            hook={"event_id": "E001-B0015", "description": "Hook"},
            cliffhanger={"event_id": "E001-B0005", "unresolved_question": "Why?"},
            why_it_works="Out of bounds test",
            theme="test",
        )
        validated = validate_candidate_draft(out_of_bounds_draft, m1, run_id="test", all_manifests_map=self.manifest_map)
        self.assertFalse(validated.is_valid)
        self.assertTrue(any("outside the selected footage" in err for err in validated.validation_errors))

    def test_all_episodes_analyzed(self):
        for m in self.manifests:
            analysis = self.provider.generate_analysis(m)
            self.assertIn(analysis.status, ("success", "no_candidate", "failed"))
            if analysis.status == "no_candidate":
                self.assertIsNotNone(analysis.reason)
            else:
                self.assertGreater(len(analysis.candidates), 0)
                self.assertLessEqual(len(analysis.candidates), 3)

    def test_accepted_candidates_meet_all_contracts(self):
        for m in self.manifests:
            analysis = self.provider.generate_analysis(m)
            if analysis.status == "success":
                for draft in analysis.candidates:
                    val = validate_candidate_draft(draft, m, run_id="test", all_manifests_map=self.manifest_map)
                    self.assertTrue(val.is_valid, f"Candidate {val.candidate_id} failed validation: {val.validation_errors}")
                    self.assertGreaterEqual(val.total_duration_sec, 20.0)
                    self.assertLessEqual(val.total_duration_sec, 60.0)
                    self.assertLessEqual(val.hook.get("offset_sec", 99), 3.0)

    def test_sequential_ranking_no_rank_zero(self):
        all_cands = []
        for m in self.manifests[:5]:
            analysis = self.provider.generate_analysis(m)
            for d in analysis.candidates:
                v = validate_candidate_draft(d, m, run_id="test", all_manifests_map=self.manifest_map)
                all_cands.append(v)

        deduped, _ = deduplicate_candidates(all_cands)
        ranked_all, top10, _ = select_and_rank_candidates(deduped, top_k=5)
        ranks = [c.rank for c in ranked_all]
        self.assertEqual(ranks, list(range(1, len(ranked_all) + 1)))
        self.assertNotIn(0, ranks)


if __name__ == "__main__":
    unittest.main()
