"""
Independent Release Audit for promofinder Problem 1 Prototype.
Conforms strictly to Section 5 release audit requirements.
Recomputes and verifies all invariants from raw artifacts rather than trusting run_facts.json.
"""

from __future__ import annotations
import csv
import json
import os
import unittest
from pathlib import Path


class TestReleaseAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_dir = Path(os.environ.get("PROMOFINDER_CANONICAL_RUN", "runs/canonical"))
        cls.has_run = cls.run_dir.exists() and (cls.run_dir / "run_facts.json").exists()

    def test_release_audit_canonical_run(self):
        """Executes full independent release audit across run artifacts if present."""
        if not self.has_run:
            self.skipTest("No canonical run directory found to audit. Set PROMOFINDER_CANONICAL_RUN to enable.")

        # 1. Manifest verification
        manifest_file = self.run_dir / "manifest.json"
        self.assertTrue(manifest_file.exists(), "Missing manifest.json")
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        total_eps = manifest_data["episode_count"]

        # 2. Raw candidates verification
        cand_file = self.run_dir / "candidates.jsonl"
        self.assertTrue(cand_file.exists(), "Missing candidates.jsonl")
        all_candidates = []
        with open(cand_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    all_candidates.append(json.loads(line))

        valid_cands = [c for c in all_candidates if c.get("is_valid", False)]
        self.assertEqual(len(valid_cands), len(all_candidates), "All candidates in candidates.jsonl must have is_valid=True")

        # Independent candidate yield and coverage calculation
        episodes_with_valid = {c["episode"] for c in valid_cands}
        computed_success_eps = len(episodes_with_valid)

        # 3. Rejections verification
        rej_file = self.run_dir / "rejections.jsonl"
        computed_no_cand_eps = set()
        if rej_file.exists():
            with open(rej_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        r = json.loads(line)
                        if r.get("rejection_type") == "NO_QUALIFYING_WINDOW":
                            computed_no_cand_eps.add(r["episode"])

        computed_coverage_pct = round(((computed_success_eps + len(computed_no_cand_eps)) / total_eps) * 100.0, 1)
        self.assertEqual(computed_coverage_pct, 100.0, "Derived processing coverage must be exactly 100.0%")

        # 4. Mechanical validity invariant: hook completion <= 3000ms
        for c in valid_cands:
            hook_complete = c.get("hook_complete_by_ms", 99999)
            self.assertLessEqual(hook_complete, 3000, f"Candidate {c['candidate_id']} has hook_complete_by_ms={hook_complete} > 3000")
            self.assertTrue(c.get("hook_within_3s", False))
            self.assertLessEqual(c.get("hook_offset_ms", 99999), 3000)
            self.assertGreaterEqual(c.get("total_duration_sec", 0), 20.0)
            self.assertLessEqual(c.get("total_duration_sec", 999), 60.0)
            self.assertEqual(len(c.get("validation_errors", [])), 0)

        # 5. Top 10 and Top 3 verification
        top10_file = self.run_dir / "exports" / "top10_diverse_promos.json"
        self.assertTrue(top10_file.exists(), "Missing top10_diverse_promos.json")
        with open(top10_file, "r", encoding="utf-8") as f:
            top10 = json.load(f)

        ranks = [c["rank"] for c in top10]
        self.assertEqual(ranks, list(range(1, len(top10) + 1)), "Top-10 ranks must be contiguous 1..N")

        top3_file = self.run_dir / "top3_delivery.json"
        self.assertTrue(top3_file.exists(), "Missing top3_delivery.json")
        with open(top3_file, "r", encoding="utf-8") as f:
            top3 = json.load(f)

        self.assertEqual(len(top3["first_to_post_promos"]), min(3, len(top10)))
        for i, p in enumerate(top3["first_to_post_promos"], 1):
            self.assertEqual(p["rank"], i)
            self.assertIn("why_it_works", p)
            self.assertTrue(p["why_it_works"].strip())
            self.assertIn("unresolved_question", p["cliffhanger"])
            self.assertTrue(p["cliffhanger"]["unresolved_question"].strip())

        # 6. JSON vs CSV parity verification
        csv_file = self.run_dir / "exports" / "top10_diverse_promos.csv"
        self.assertTrue(csv_file.exists(), "Missing top10_diverse_promos.csv")
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)

        self.assertEqual(len(csv_rows), len(top10))
        for j_item, c_item in zip(top10, csv_rows):
            self.assertEqual(j_item["candidate_id"], c_item["candidate_id"])
            self.assertEqual(str(j_item["rank"]), c_item["rank"])
            self.assertEqual(f"{j_item['total_duration_sec']:.1f}", f"{float(c_item['total_duration_sec']):.1f}")

        # 7. run_facts.json agreement
        facts_file = self.run_dir / "run_facts.json"
        self.assertTrue(facts_file.exists(), "Missing run_facts.json")
        with open(facts_file, "r", encoding="utf-8") as f:
            facts = json.load(f)

        self.assertEqual(facts["total_episodes"], total_eps)
        self.assertEqual(facts["coverage_and_yield"]["processing_coverage_pct"], 100.0)
        self.assertEqual(facts["coverage_and_yield"]["success_episodes_count"], computed_success_eps)
        self.assertEqual(facts["candidate_accounting"]["total_mechanically_valid"], len(valid_cands))
        self.assertEqual(facts["model_execution_disclosure"]["known_paid_api_cost_usd"], 0.00)
        self.assertEqual(facts["model_execution_disclosure"]["external_model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
