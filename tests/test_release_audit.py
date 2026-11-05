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
        self.assertEqual(total_eps, 50, "Manifest must record exactly 50 episodes.")
        events_file = self.run_dir / "events.jsonl"
        self.assertTrue(events_file.exists(), "Missing events.jsonl")
        with open(events_file, "r", encoding="utf-8") as f:
            actual_event_count = sum(1 for line in f if line.strip())
        self.assertEqual(
            manifest_data["total_events"],
            actual_event_count,
            "Manifest event count must equal the supplied canonical event stream.",
        )

        # 2. Episode status arithmetic from raw analyses
        raw_dir = self.run_dir / "raw"
        self.assertTrue(raw_dir.exists(), "Missing raw/ analysis directory")
        analyses = []
        for p in sorted(raw_dir.glob("analysis_ep*.json")):
            with open(p, "r", encoding="utf-8") as f:
                analyses.append(json.load(f))
        self.assertEqual(len(analyses), 50, "Exactly 50 raw episode analyses required.")

        status_counts = {"success": 0, "no_candidate": 0, "pending": 0, "failed": 0}
        no_candidate_eps = []
        for a in analyses:
            st = a["status"]
            status_counts[st] = status_counts.get(st, 0) + 1
            if st == "no_candidate":
                no_candidate_eps.append(a["episode"])

        total_status = sum(status_counts.values())
        self.assertEqual(total_status, 50, f"Status total {total_status} != 50")
        self.assertEqual(status_counts["pending"], 0, "Zero pending episodes allowed in canonical run.")
        self.assertEqual(status_counts["failed"], 0, "Zero failed episodes allowed in canonical run.")

        success_cnt = status_counts["success"]
        no_cand_cnt = status_counts["no_candidate"]
        calc_coverage = round((success_cnt + no_cand_cnt) / 50.0 * 100.0, 1)
        calc_yield = round(success_cnt / 50.0 * 100.0, 1)
        self.assertEqual(calc_coverage, 100.0, "Processing coverage must equal 100.0%")

        # 3. Candidate accounting: valid + rejected == total drafts
        val_file = self.run_dir / "validated" / "all_validated_candidates.json"
        rej_file = self.run_dir / "rejected" / "all_rejected_candidates.json"
        self.assertTrue(val_file.exists(), "Missing all_validated_candidates.json")
        self.assertTrue(rej_file.exists(), "Missing all_rejected_candidates.json")

        with open(val_file, "r", encoding="utf-8") as f:
            valid_cands = json.load(f)
        with open(rej_file, "r", encoding="utf-8") as f:
            rej_cands = json.load(f)

        total_drafts = len(valid_cands) + len(rej_cands)
        self.assertGreater(total_drafts, 0, "Generated drafts must be > 0")

        # 4. Invariant: Every valid candidate must strictly satisfy every hard gate
        for c in valid_cands:
            self.assertTrue(c["is_valid"], f"Candidate {c['candidate_id']} has is_valid=False in validated list.")
            self.assertTrue(c["duration_valid"], f"Candidate {c['candidate_id']} duration_valid is False.")
            self.assertTrue(20000 <= c["total_duration_ms"] <= 60000, f"Candidate {c['candidate_id']} duration out of bounds.")
            self.assertTrue(c["source_events_present"], f"Candidate {c['candidate_id']} missing source events.")
            self.assertEqual(c["boundary_conflicts"], 0, f"Candidate {c['candidate_id']} has boundary conflicts.")
            self.assertTrue(0 <= c["hook_offset_ms"] <= 3000, f"Candidate {c['candidate_id']} hook offset > 3s.")
            self.assertTrue(c["hook_within_3s"], f"Candidate {c['candidate_id']} hook_within_3s is False.")
            self.assertTrue(0 <= c["hook_complete_by_ms"] <= 3000, f"Candidate {c['candidate_id']} hook completes after 3s ({c['hook_complete_by_ms']}ms).")
            self.assertTrue(c["cliff_near_end"], f"Candidate {c['candidate_id']} cliff_near_end is False.")
            self.assertTrue(0 <= c["cliff_gap_ms"] <= 3000, f"Candidate {c['candidate_id']} cliff gap > 3s.")
            self.assertEqual(c["answer_events_after_cliff"], 0, f"Candidate {c['candidate_id']} has answer events after cliff.")
            self.assertEqual(len(c["validation_errors"]), 0, f"Candidate {c['candidate_id']} has validation errors.")

            # Zero subjective scoring fields
            for forbidden in ["scores", "score_reasons", "composite_score", "hook_strength", "cliffhanger_strength", "standalone_clarity", "pacing"]:
                self.assertNotIn(forbidden, c, f"Candidate {c['candidate_id']} contains forbidden field '{forbidden}'.")

        # 5. Invariant: Every rejected candidate must have is_valid=False and at least one explicit error
        for r in rej_cands:
            self.assertFalse(r["is_valid"], f"Rejected candidate {r['candidate_id']} has is_valid=True.")
            self.assertGreater(len(r["validation_errors"]), 0, f"Rejected candidate {r['candidate_id']} lacks error reasons.")

        # 6. Ranked outputs: unique sequential ranks and valid relative rank percentiles
        ranked_file = self.run_dir / "exports" / "ranked_all_candidates.json"
        self.assertTrue(ranked_file.exists(), "Missing ranked_all_candidates.json")
        with open(ranked_file, "r", encoding="utf-8") as f:
            ranked_all = json.load(f)

        n_ranked = len(ranked_all)
        self.assertEqual(n_ranked, len(valid_cands), "Ranked count must match validated candidates count.")
        for expected_rank, c in enumerate(ranked_all, 1):
            self.assertEqual(c["rank"], expected_rank, f"Rank mismatch at index {expected_rank}: got {c['rank']}.")
            expected_pct = round(100.0 * (n_ranked - expected_rank) / max(n_ranked - 1, 1), 2)
            self.assertEqual(c["rank_percentile"], expected_pct, f"Percentile mismatch for rank {expected_rank}.")

        # 7. Top 10 JSON vs CSV field-by-field agreement
        top10_json_file = self.run_dir / "exports" / "top10_diverse_promos.json"
        top10_csv_file = self.run_dir / "exports" / "top10_diverse_promos.csv"
        self.assertTrue(top10_json_file.exists(), "Missing top10_diverse_promos.json")
        self.assertTrue(top10_csv_file.exists(), "Missing top10_diverse_promos.csv")

        with open(top10_json_file, "r", encoding="utf-8") as f:
            top10_json = json.load(f)
        with open(top10_csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            top10_csv = list(reader)

        self.assertEqual(len(top10_json), len(top10_csv), "Top 10 JSON and CSV row count mismatch.")
        for j_item, c_item in zip(top10_json, top10_csv):
            self.assertEqual(j_item["candidate_id"], c_item["candidate_id"])
            self.assertEqual(j_item["episode"], int(c_item["episode"]))
            self.assertEqual(j_item["rank"], int(c_item["rank"]))
            self.assertAlmostEqual(j_item["total_duration_sec"], float(c_item["total_duration_sec"]), places=2)

        # 8. run_facts.json agreement with recomputed numbers
        facts_file = self.run_dir / "run_facts.json"
        self.assertTrue(facts_file.exists(), "Missing run_facts.json")
        with open(facts_file, "r", encoding="utf-8") as f:
            facts = json.load(f)

        self.assertEqual(facts["parser_accounting"]["parsed_timed_blocks"], actual_event_count)
        self.assertEqual(facts["coverage_and_yield"]["success_episodes_count"], success_cnt)
        self.assertEqual(facts["coverage_and_yield"]["no_candidate_episodes_count"], no_cand_cnt)
        self.assertEqual(facts["coverage_and_yield"]["processing_coverage_pct"], calc_coverage)
        self.assertEqual(facts["coverage_and_yield"]["candidate_episode_yield_pct"], calc_yield)
        self.assertEqual(facts["candidate_accounting"]["mechanically_valid_candidates"], len(valid_cands))
        self.assertEqual(facts["candidate_accounting"]["rejected_candidates"], len(rej_cands))
        self.assertEqual(facts["model_execution_disclosure"]["known_paid_api_cost_usd"], 0.00)
        self.assertEqual(facts["model_execution_disclosure"]["external_model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
