"""
Regression tests for the wording and labelling of generated output.
They use only the synthetic sample, so they run in the public repository too.
"""
import unittest
from pathlib import Path

from promofinder.parser import parse_screenplay_file
from promofinder.provider import DeterministicBaselineProvider
from promofinder.evaluate import audit_stress_cases


class TestOutputTextHonesty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sample = Path("sample_input/episode-001.txt")
        if not sample.exists():
            raise unittest.SkipTest("sample_input/episode-001.txt not found.")
        cls.manifest = parse_screenplay_file(sample)
        cls.analysis = DeterministicBaselineProvider().generate_analysis(cls.manifest)

    def test_why_it_works_uses_the_candidates_own_facts(self):
        c = self.analysis.candidates[0]
        events = {e.event_id: e for e in self.manifest.events}
        hook_text = events[c.hook["event_id"]].text.strip(' "')
        cliff_text = events[c.cliffhanger["event_id"]].text.strip(' "')
        # long quotes are shortened to 70 characters, so compare the opening words
        self.assertIn(hook_text[:40], c.why_it_works)
        self.assertIn(cliff_text[:40], c.why_it_works)
        self.assertNotIn("immediate high-stakes", c.why_it_works)

    def test_standalone_summary_does_not_claim_a_new_viewer_understands_it(self):
        for c in self.analysis.candidates:
            text = c.standalone_summary.lower()
            self.assertNotIn("self-contained", text)
            self.assertIn("has not been verified", text)

    def test_theme_uses_whole_words_only(self):
        p = DeterministicBaselineProvider()
        self.assertEqual(p._determine_theme("He hit his elbow on the border."), "dramatic_confrontation")
        self.assertEqual(p._determine_theme("They talk about the wedding and the gown."), "wedding_betrayal")

    def test_stress_report_never_says_verified(self):
        reports = audit_stress_cases({}, [], [])
        self.assertTrue(reports)
        for r in reports:
            self.assertNotIn("verified", (r["verdict"] + r["audit"]).lower().replace("not verified", ""))
            self.assertIn("human review", r["verdict"].lower())


if __name__ == "__main__":
    unittest.main()
