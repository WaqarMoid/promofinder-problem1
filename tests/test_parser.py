"""
Unit tests for screenplay parser and contracts.
Conforms to acceptance criteria for screenplay ingestion.
"""

import os
import json
import unittest
from pathlib import Path

from promofinder.parser import parse_all_episodes
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
        self.assertEqual(len(self.manifests), len(self.inventory["episodes"]))
        ep_numbers = [m.episode for m in self.manifests]
        self.assertEqual(ep_numbers, list(range(1, len(self.inventory["episodes"]) + 1)))

    def test_total_event_count_matches_inventory(self):
        total_events = sum(len(m.events) for m in self.manifests)
        self.assertEqual(total_events, self.inventory["total_events"])

    def test_total_duration_matches_inventory(self):
        total_duration_ms = sum(m.duration_ms for m in self.manifests)
        self.assertEqual(total_duration_ms, self.inventory["total_duration_ms"])

    def test_sha256_hashes_match_inventory(self):
        inv_map = {item["episode"]: item for item in self.inventory["episodes"]}
        for m in self.manifests:
            inv = inv_map[m.episode]
            self.assertEqual(m.sha256, inv["sha256"], f"SHA256 mismatch in ep {m.episode}")
            self.assertEqual(len(m.events), inv["timed_event_count"], f"Event count mismatch in ep {m.episode}")
            self.assertEqual(m.duration_ms, inv["duration_ms"], f"Duration mismatch in ep {m.episode}")

    def test_events_have_nonblank_text_and_valid_types(self):
        for m in self.manifests:
            for ev in m.events:
                self.assertTrue(ev.text.strip(), f"Blank text in event {ev.event_id}")
                self.assertIn(ev.kind, ("camera", "action", "dialogue", "sound"))

    def test_start_order_regressions_detected(self):
        total_regressions = sum(len(m.start_regressions) for m in self.manifests)
        self.assertGreater(total_regressions, 0)


if __name__ == "__main__":
    unittest.main()
