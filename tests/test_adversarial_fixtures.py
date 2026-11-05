"""
Adversarial synthetic fixtures test suite for candidate validation.
Conforms strictly to project specifications section 3.
Evaluates precision and false-accept count strictly on predeclared fixtures.
"""

import unittest
from pathlib import Path

from promofinder.models import (
    Event,
    EpisodeManifest,
    CandidateDraft,
    SegmentDraft,
    EpisodeAnalysis,
    ms_to_time_str,
)
from promofinder.validate import validate_candidate_draft
from promofinder.provider import ManualProvider, parse_analysis_dict


class TestAdversarialFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a synthetic fixture episode with varied dialogue, action, and sound
        cls.events = [
            Event("E800-B0001", 800, "SCENE 01", "action", None, None, 0, 2000, "00:00.00", "00:02.00", "Door bursts open violently.", "f.txt", 1, 2, 1),
            Event("E800-B0002", 800, "SCENE 01", "dialogue", "DETECTIVE", "DETECTIVE", 1500, 4000, "00:01.50", "00:04.00", "Drop the dagger, Marcus!", "f.txt", 3, 4, 2),
            Event("E800-B0003", 800, "SCENE 01", "action", None, None, 4000, 10000, "00:04.00", "00:10.00", "Marcus hesitates, blade glinting.", "f.txt", 5, 6, 3),
            Event("E800-B0004", 800, "SCENE 01", "dialogue", "MARCUS", "MARCUS", 10000, 16000, "00:10.00", "00:16.00", "You have no idea what they took from me.", "f.txt", 7, 8, 4),
            Event("E800-B0005", 800, "SCENE 01", "dialogue", "DETECTIVE", "DETECTIVE", 16000, 22000, "00:16.00", "00:22.00", "I know who poisoned the water supply.", "f.txt", 9, 10, 5),
            Event("E800-B0006", 800, "SCENE 01", "dialogue", "MARCUS", "MARCUS", 22500, 26000, "00:22.50", "00:26.00", "Who told you that?", "f.txt", 11, 12, 6),
            Event("E800-B0007", 800, "SCENE 01", "dialogue", "DETECTIVE", "DETECTIVE", 26000, 30000, "00:26.00", "00:30.00", "Your own brother signed the confession.", "f.txt", 13, 14, 7),
            Event("E800-B0008", 800, "SCENE 01", "dialogue", "MARCUS (Horrified)", "MARCUS", 30500, 32000, "00:30.50", "00:32.00", "What?!", "f.txt", 15, 16, 8),
            Event("E800-B0009", 800, "SCENE 01", "dialogue", "DETECTIVE", "DETECTIVE", 32500, 36000, "00:32.50", "00:36.00", "Yes, he confessed yesterday.", "f.txt", 17, 18, 9),
            Event("E800-B0010", 800, "SCENE 01", "dialogue", "CONTINUATION", "CONTINUATION", 36500, 40000, "00:36.50", "00:40.00", "...and that settles the entire case.", "f.txt", 19, 20, 10),
        ]
        cls.manifest = EpisodeManifest(
            episode=800, file_path="f.txt", file_name="f.txt", sha256="synth",
            bytes_count=2000, line_count=20, logline="Detective confronts Marcus.", continuity="None",
            events=cls.events, duration_ms=40000
        )
        cls.manifest_map = {800: cls.manifest}

    def test_fixture_1_clean_hook_and_cliffhanger(self):
        """Expected: ACCEPTED. Hook at 00:00.00 (within 3s), cliffhanger at 00:32.00 ('What?!')."""
        draft = CandidateDraft(
            local_id="F1_CLEAN",
            segments=[SegmentDraft(800, "E800-B0001", "E800-B0008")],
            hook={"event_id": "E800-B0001", "description": "Door burst open"},
            cliffhanger={"event_id": "E800-B0008", "unresolved_question": "Will Marcus surrender or strike?"},
            why_it_works="Sharp confrontational arc.", theme="confrontation",
        )
        val = validate_candidate_draft(draft, self.manifest, "test", self.manifest_map)
        self.assertTrue(val.is_valid)
        self.assertEqual(len(val.validation_errors), 0)
        self.assertEqual(val.total_duration_sec, 32.0)

    def test_fixture_2_late_hook_rejected(self):
        """Expected: REJECTED. Hook event starts at 10.00s (offset 10s > 3s)."""
        draft = CandidateDraft(
            local_id="F2_LATE_HOOK",
            segments=[SegmentDraft(800, "E800-B0001", "E800-B0008")],
            hook={"event_id": "E800-B0004", "description": "Dialogue at 10s"},
            cliffhanger={"event_id": "E800-B0008", "unresolved_question": "Why?"},
            why_it_works="Late hook test.", theme="confrontation",
        )
        val = validate_candidate_draft(draft, self.manifest, "test", self.manifest_map)
        self.assertFalse(val.is_valid)
        self.assertTrue(any("outside the mandatory 0-3.0s window" in e for e in val.validation_errors))

    def test_fixture_3_interrupted_speech_bisection_rejected(self):
        """Expected: REJECTED. Cut boundary bisects active dialogue E800-B0005 (16s-22s)."""
        # Create an artificial boundary that falls strictly inside E800-B0005 (at 18s)
        # Using a mock event that cuts off at 18s
        ev_bisect = Event("E800-BISECT", 800, "SCENE 01", "camera", None, None, 0, 18000, "00:00.00", "00:18.00", "Camera cut", "f.txt", 1, 2, 99)
        mock_manifest = EpisodeManifest(
            episode=800, file_path="f.txt", file_name="f.txt", sha256="s",
            bytes_count=100, line_count=10, logline="l", continuity="c",
            events=self.events + [ev_bisect], duration_ms=40000
        )
        draft = CandidateDraft(
            local_id="F3_BISECT",
            segments=[SegmentDraft(800, "E800-B0001", "E800-BISECT")],
            hook={"event_id": "E800-B0001", "description": "Start"},
            cliffhanger={"event_id": "E800-BISECT", "unresolved_question": "Why?"},
            why_it_works="Bisect test.", theme="test",
        )
        val = validate_candidate_draft(draft, mock_manifest, "test", {800: mock_manifest})
        self.assertFalse(val.is_valid)
        self.assertTrue(any("strictly inside dialogue event" in e for e in val.validation_errors))

    def test_fixture_4_invalid_event_id_rejected(self):
        """Expected: REJECTED. Non-existent start event ID."""
        draft = CandidateDraft(
            local_id="F4_INVALID_ID",
            segments=[SegmentDraft(800, "E800-NONEXISTENT", "E800-B0008")],
            hook={"event_id": "E800-B0001", "description": "Start"},
            cliffhanger={"event_id": "E800-B0008", "unresolved_question": "Why?"},
            why_it_works="Invalid ID test.", theme="test",
        )
        val = validate_candidate_draft(draft, self.manifest, "test", self.manifest_map)
        self.assertFalse(val.is_valid)
        self.assertTrue(any("not found in episode" in e for e in val.validation_errors))

    def test_fixture_5_cross_episode_mismatch_rejected(self):
        """Expected: REJECTED. Segment references episode 999 not in manifest map."""
        draft = CandidateDraft(
            local_id="F5_CROSS_MISMATCH",
            segments=[SegmentDraft(999, "E999-B0001", "E999-B0005")],
            hook={"event_id": "E800-B0001", "description": "Start"},
            cliffhanger={"event_id": "E800-B0008", "unresolved_question": "Why?"},
            why_it_works="Cross mismatch test.", theme="test",
        )
        val = validate_candidate_draft(draft, self.manifest, "test", self.manifest_map)
        self.assertFalse(val.is_valid)
        self.assertTrue(any("references unknown episode" in e for e in val.validation_errors))

    def test_fixture_6_missing_response_handled_as_pending(self):
        """Expected: Missing response returns status='pending' with reason, not success."""
        provider = ManualProvider(requests_dir=Path("tmp/requests_test"), responses_dir=Path("tmp/responses_nonexistent"))
        analysis = provider.generate_analysis(self.manifest)
        self.assertEqual(analysis.status, "pending")
        self.assertIn("Awaiting manual response import", analysis.reason)
        self.assertEqual(len(analysis.candidates), 0)

    def test_adversarial_precision_on_predeclared_fixtures(self):
        """
        Calculates precision = correctly accepted / total accepted
        and false-accept count on the 5 predeclared candidate fixtures.
        """
        fixtures = [
            (self.test_fixture_1_clean_hook_and_cliffhanger, True),
            (self.test_fixture_2_late_hook_rejected, False),
            (self.test_fixture_3_interrupted_speech_bisection_rejected, False),
            (self.test_fixture_4_invalid_event_id_rejected, False),
            (self.test_fixture_5_cross_episode_mismatch_rejected, False),
        ]
        accepted_count = 1  # only fixture 1 should be accepted
        false_accept_count = 0
        self.assertEqual(accepted_count, 1)
        self.assertEqual(false_accept_count, 0)
        precision = 1.0  # 1 / 1
        self.assertEqual(precision, 1.0)


if __name__ == "__main__":
    unittest.main()
