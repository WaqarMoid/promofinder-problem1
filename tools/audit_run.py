"""
Independent audit of a promofinder run folder.

Reads only events.jsonl, candidates.jsonl, episode_analyses.jsonl and the exports,
and re-derives every count and timing check without using the promofinder package.

Usage:  python src/audit_run.py runs/run_v6
Exit code is 0 when every check passes, 1 otherwise.
"""
import collections
import csv
import json
import sys
from pathlib import Path


def load_jsonl(p):
    return [json.loads(line) for line in open(p, encoding="utf-8") if line.strip()]


def main(run_dir):
    R = Path(run_dir)
    ev = load_jsonl(R / "events.jsonl")
    cands = load_jsonl(R / "candidates.jsonl")
    analyses = load_jsonl(R / "episode_analyses.jsonl")
    by_id = {e["event_id"]: e for e in ev}
    by_ep = collections.defaultdict(list)
    for e in ev:
        by_ep[e["episode"]].append(e)

    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    status = collections.Counter(a["status"] for a in analyses)
    expected = json.load(open(R / "manifest.json", encoding="utf-8"))["episode_count"]
    check(f"{expected} episodes in events", len(by_ep) == expected, f"{len(by_ep)} episodes, {len(ev)} events")
    check(f"{expected} episode analyses", len(analyses) == expected, dict(status))
    check("status arithmetic", sum(status.values()) == expected)
    check("candidate count matches analyses", len(cands) == sum(len(a.get("candidates", [])) for a in analyses),
          f"{len(cands)} candidates")
    eps_with = {c["episode"] for c in cands}
    check("success episodes == episodes with candidates", status["success"] == len(eps_with),
          f"{status['success']} vs {len(eps_with)}")

    bad = collections.Counter()
    for c in cands:
        segs = c["segments"]
        total, prev = 0, -1
        for s in segs:
            d = s["end_ms"] - s["start_ms"]
            total += d
            if d <= 0 or d != s["duration_ms"]:
                bad["segment_duration"] += 1
            if s["start_ms"] < prev:
                bad["segment_order"] += 1
            prev = s["end_ms"]
            for e in by_ep[s["episode"]]:
                if e["kind"] == "dialogue" and (e["start_ms"] < s["start_ms"] < e["end_ms"]
                                                or e["start_ms"] < s["end_ms"] < e["end_ms"]):
                    bad["dialogue_bisected"] += 1
                    break
        if not 20000 <= total <= 60000:
            bad["duration_out_of_range"] += 1
        if total != c["total_duration_ms"]:
            bad["total_duration_mismatch"] += 1
        s0, s1 = segs[0], segs[-1]
        h, k = by_id[c["hook"]["event_id"]], by_id[c["cliffhanger"]["event_id"]]
        off, done = h["start_ms"] - s0["start_ms"], h["end_ms"] - s0["start_ms"]
        if not (0 <= off <= 3000 and done <= 3000):
            bad["hook_gate"] += 1
        if (off, done) != (c["hook_offset_ms"], c["hook_complete_by_ms"]):
            bad["hook_fields_mismatch"] += 1
        gap = s1["end_ms"] - k["end_ms"]
        if not 0 <= gap <= 3000:
            bad["cliff_gap_gate"] += 1
        if gap != c["cliff_gap_ms"]:
            bad["cliff_gap_mismatch"] += 1
        if k["start_ms"] < s0["start_ms"] or k["end_ms"] > s1["end_ms"]:
            bad["cliff_outside_cut"] += 1
        if any(e["kind"] == "dialogue" and e["event_id"] != k["event_id"]
               and e["start_ms"] >= k["end_ms"] and e["end_ms"] <= s1["end_ms"] for e in by_ep[c["episode"]]):
            bad["answer_after_cliff"] += 1
    check("no timing or boundary violations in any candidate", not bad, dict(bad))

    ranked = json.load(open(R / "exports" / "ranked_all_candidates.json", encoding="utf-8"))
    check("ranks are 1..N", [c["rank"] for c in ranked] == list(range(1, len(ranked) + 1)), f"{len(ranked)} ranked")
    top10 = json.load(open(R / "exports" / "top10_diverse_promos.json", encoding="utf-8"))
    top3 = json.load(open(R / "exports" / "top3_first_to_post.json", encoding="utf-8"))
    check("top3 == first 3 of top10", [t["candidate_id"] for t in top3] == [c["candidate_id"] for c in top10[:3]])
    check("top10 episodes are distinct", len({c["episode"] for c in top10}) == len(top10))
    rows = list(csv.DictReader(open(R / "exports" / "top10_diverse_promos.csv", encoding="utf-8")))
    check("top10 CSV matches JSON", [r["candidate_id"] for r in rows] == [c["candidate_id"] for c in top10])
    for t in top3:
        c = next(x for x in cands if x["candidate_id"] == t["candidate_id"])
        s = c["segments"][0]
        check(f"top3 #{t['rank']} timestamps match source",
              t["segments"] == [f"{s['start_time_str']} - {s['end_time_str']}"] and t["duration_sec"] == c["total_duration_sec"])
        check(f"top3 #{t['rank']} quotes match source events",
              by_id[c["hook"]["event_id"]]["text"].strip(' "“”') in t["hook_evidence"]
              and by_id[c["cliffhanger"]["event_id"]]["text"].strip(' "“”') in t["cliffhanger_evidence"])

    facts = json.load(open(R / "run_facts.json", encoding="utf-8"))
    check("run_facts coverage matches analyses",
          facts["coverage_and_yield"]["success_episodes_count"] == status["success"]
          and facts["coverage_and_yield"]["no_candidate_episodes_count"] == status["no_candidate"])
    check("run_facts candidate count matches",
          facts["candidate_accounting"]["mechanically_valid_candidates"] == len(cands))
    check("run_facts event count matches", facts["parser_accounting"]["parsed_timed_blocks"] == len(ev))

    kinds_h = collections.Counter(by_id[c["hook"]["event_id"]]["kind"] for c in cands)
    kinds_k = collections.Counter(by_id[c["cliffhanger"]["event_id"]]["kind"] for c in cands)
    print(f"Run audited: {R}")
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail != "" else ""))
    print(f"  info: hook event kinds {dict(kinds_h)}; cliffhanger event kinds {dict(kinds_k)}")
    print(f"  info: segments per candidate {dict(collections.Counter(len(c['segments']) for c in cands))}")
    failed = [n for n, ok, _ in results if not ok]
    print("RESULT:", "ALL CHECKS PASSED" if not failed else f"FAILED: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "runs/run_v6"))
