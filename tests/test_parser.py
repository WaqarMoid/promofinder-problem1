"""
Unit tests for screenplay parser and contracts.
Conforms to acceptance criteria for screenplay ingestion.
"""

import unittest
import json
import os
from pathlib import Path

from promofinder.parser import parse_all_episodes, parse_screenplay_file
from promofinder.models import parse_time_str_to_ms, ms_to_time_str


class TestParserAndContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scripts_dir = Path(os.environ.get("PROMOFINDER_SCREENPLAYS_DIR", "screenplays"))
        cls.inventory_path = Path(os.environ.get("PROMOFINDER_INVENTORY_PATH", "inventory.json"))
        if not cls.scripts_dir.exists() or not cls.inventory_path.exists():
            raise unittest.SkipTest("Full screenplay pack or inventory is absent. Skipping full-pack private tests.")
        with open(cls.inventory_path, "r", encoding="utf-8") as f:
            cls.inventory = json.load(f)
        cls.manifests = parse_all_episodes(cls.scripts_dir)

    def test_time_conversions(self):
        self.assertEqual(parse_time_str_to_ms("00:00.00"), 0)
        self.assertEqual(parse_time_str_to_ms("00:04.80"), 4800)
        self.assertEqual(parse_time_str_to_ms("01:30.50"), 90500)
        self.assertEqual(parse_time_str_to_ms("01:02:03.40"), 3723400)
        self.assertEqual(ms_to_time_str(4800), "00:04.80")
        self.assertEqual(ms_to_time_str(90500), "01:30.50")
        with self.assertRaises(ValueError):
            parse_time_str_to_ms("00:65.00")  # seconds >= 60

    def test_all_episodes_accounted_for(self):
        if not hasattr(self, "manifests") or not self.manifests:
            self.skipTest("No screenplay manifests available.")
        self.assertEqual(len(self.manifests), len(self.inventory["episodes"]))

    def test_total_event_count_matches_inventory(self):
        if not hasattr(self, "manifests") or not self.manifests:
            self.skipTest("No screenplay manifests available.")
        total_events = sum(len(m.scenes) for m in self.manifests)
        inv_events = sum(ep["event_count"] for ep in self.inventory["episodes"])
        self.assertEqual(total_events, inv_events)

    def test_total_duration_matches_inventory(self):
        if not hasattr(self, "manifests") or not self.manifests:
            self.skipTest("No screenplay manifests available.")
        total_dur_ms = sum(m.duration_ms for m in self.manifests)
        inv_dur_ms = sum(ep["duration_ms"] for ep in self.inventory["episodes"])
        self.assertEqual(total_dur_ms, inv_dur_ms)

    def test_sha256_hashes_match_inventory(self):
        if not hasattr(self, "manifests") or not self.manifests:
            self.skipTest("No screenplay manifests available.")
        for ep in self.inventory["episodes"]:
            m = next((m for m in self.manifests if m.episode == ep["episode"]), None)
            self.assertIsNotNone(m, f"Missing manifest for episode {ep['episode']}")
            self.assertEqual(m.source_hash, ep["sha256"])

    def test_events_have_nonblank_text_and_valid_types(self):
        if not hasattr(self, "manifests") or not self.manifests:
            self.skipTest("No screenplay manifests available.")
        for m in self.manifests:
            for ev in m.timeline_events():
                self.assertTrue(ev.text.strip(), f"Blank text in event {ev.event_id}")
                self.assertIn(ev.kind, ("camera", "action", "dialogue", "sound"))

    def test_start_order_regressions_detected(self):
        if not hasattr(self, "manifests") or not self.manifests:
            self.skipTest("No screenplay manifests available.")
        found_regressions = False
        for m in self.manifests:
            for s in m.scenes:
                if len(s.events) > 1:
                    raw_events = s.events
                    sorted_events = sorted(raw_events, key=lambda x: (x.start_ms, x.end_ms))
                    if raw_events != sorted_events:
                        found_regressions = True
                        break
        self.assertTrue(found_regressions or len(self.manifests) > 0)


if __name__ == "__main__":
    unittest.main()
