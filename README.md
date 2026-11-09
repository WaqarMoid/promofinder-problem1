# PromoFinder

A small command-line tool that reads microdrama screenplays and proposes promo clips: 20–60 second cuts that open on a hook, end on an open moment, and keep exact episode timestamps.

It was built for Problem 1 of the Kuku AI Generalist Assignment. It uses plain Python rules. It does not call any AI model while it runs.

---

## What it does

For every episode it:

1. **Parses** the screenplay into timed events (dialogue, action, camera, sound).
2. **Proposes cuts** by sliding a window over the events.
3. **Checks each cut** against hard rules:
   - Length is between 20.0 s and 60.0 s.
   - A hook beat starts and finishes inside the first 3.0 s.
   - No cut starts or ends in the middle of a spoken line.
   - The cut ends within 3.0 s of a cliffhanger beat.
   - No answering line follows the cliffhanger inside the cut.
4. **Removes near-duplicates** (time overlap of 70% or more on the same episode).
5. **Ranks** what is left and writes JSON, CSV and an HTML report.

### What the checks mean (and do not mean)

- The hard rules check **timestamps and boundaries**. Passing them does not show that a promo works on viewers.
- The hook and the cliffhanger are picked with **keyword and punctuation rules**. A hook is usually a spoken line, but it can also be a camera or action direction.
- "Standalone" clarity is **not verified**. The tool cannot tell if a new viewer will follow the clip.
- Ranking order comes from simple rules: the rule checks first, then how fast the hook finishes, then how close the cliffhanger is to the end. It is a ranking hypothesis, not a measure of audience response.
- Click-through, retention and comprehension were not measured.
- Candidates are checked by the same rules that produce them, so "all candidates pass" is expected and is not a quality score.

---

## Install

The tool needs only **Python 3.10 or newer** and the standard library. There is nothing to install.

```bash
git clone https://github.com/WaqarMoid/promofinder-problem1.git
cd promofinder-problem1
```

---

## Quickstart (synthetic example)

`sample_input/episode-001.txt` is a short made-up screenplay.

```bash
python -m promofinder ingest   --input sample_input --run runs/demo_run
python -m promofinder analyze  --run runs/demo_run --provider baseline
python -m promofinder finalize --run runs/demo_run --top-k 10
python -m promofinder evaluate --run runs/demo_run
```

This finds one valid promo: `00:00.00 - 00:32.00` (32.0 s). The hook finishes 2.5 s in and the cliffhanger line starts at 00:28.00.

Open `runs/demo_run/report.html` in a browser to see it.

### Files written to `runs/<name>/`

| File | What it holds |
|---|---|
| `manifest.json` | Episode list, durations, source hashes |
| `events.json`, `events.jsonl` | Every parsed event with exact timestamps |
| `episode_analyses.jsonl`, `raw/` | Per-episode result, including why an episode had no candidate |
| `candidates.jsonl` | Every cut that passed the checks |
| `rejected.jsonl`, `rejected/` | Cuts that failed, with reasons |
| `ranked_promos.json`, `ranked_promos.csv` | The top 10 (one per episode) |
| `exports/ranked_all_candidates.json`, `.csv` | All candidates in rank order |
| `exports/top10_diverse_promos.json`, `.csv` | Top 10 from different episodes |
| `exports/top3_first_to_post.json` | The three suggested first posts, with evidence |
| `run_facts.json`, `metrics.json`, `cost.json`, `timings.json` | Counts, timings, cost (zero model calls) |
| `baseline_candidates.json` | A naive "last 30 seconds" baseline for comparison |
| `failures.md` | Known ways the tool can pick badly |
| `report.html` | Self-contained report |

---

## Tests

Public-only (no private data needed):

```bash
python -m unittest discover -s tests -v
```

This discovers 24 tests. 19 pass and 5 skip, because the skipped ones need a full screenplay pack that is not in this repository.

Full mode, for someone who has the screenplay pack and a finished run:

```bash
# Linux / macOS
export PROMOFINDER_SCREENPLAYS_DIR="/path/to/screenplays"
export PROMOFINDER_INVENTORY_PATH="/path/to/inventory.json"
export PROMOFINDER_CANONICAL_RUN="/path/to/runs/run_folder"
python -m unittest discover -s tests -v
```

```powershell
# Windows PowerShell
$env:PROMOFINDER_SCREENPLAYS_DIR="D:\path\to\screenplays"
$env:PROMOFINDER_INVENTORY_PATH="D:\path\to\inventory.json"
$env:PROMOFINDER_CANONICAL_RUN="D:\path\to\runs\run_folder"
python -m unittest discover -s tests -v
```

In this mode all 38 tests run.

### Independent audit of a run

`tools/audit_run.py` re-checks a finished run without using the `promofinder` package. It recomputes episode and candidate counts, durations, segment order, dialogue-boundary checks, hook and cliffhanger timing, ranking order, and the Top 3 against the source events.

```bash
python tools/audit_run.py runs/demo_run
```

It exits with 0 when every check passes.

---

## Using a model instead of rules

The baseline provider is rule-based. To try a model:

```bash
python -m promofinder requests --run runs/demo_run --provider manual
```

This writes one prompt file per episode to `runs/demo_run/requests/`. Send each prompt to any model, save its JSON reply as `runs/demo_run/responses/response_epNNN.json`, then run `analyze --provider manual`. The model only chooses event IDs. The same code then computes the timestamps and applies every check above, so a model cannot return an invalid cut. Calling a hosted API directly is switched off in this prototype.

---

## Code layout

```
promofinder/
  cli.py        command-line commands
  config.py     limits (20–60 s, 3 s)
  parser.py     screenplay -> timed events
  provider.py   cut proposals: rule-based provider, and prompt export/import for a model
  validate.py   hard checks on every cut
  rank.py       de-duplication, ranking, top-10 selection, CSV/JSON export
  evaluate.py   metrics, baseline comparison, run_facts.json
  export.py     delivery files and failures.md
  viewer.py     report.html
  models.py     data classes and timestamp helpers
  pipeline.py   runs the stages
tools/audit_run.py   independent audit of a finished run
sample_input/        a short synthetic screenplay
tests/               unit tests (synthetic) and full-pack tests (skipped without the pack)
```

---

## Limits

- Screenplay text cannot show acting, voice, pacing or framing. A person must check the filmed clip.
- Only single continuous cuts are proposed. Joining moments or episodes is not implemented.
- Rules are keyword based and were tuned on one show, so they may fit other shows worse.
- Some hooks and cliffhangers are camera or action directions rather than spoken lines.
- No content-safety check is made. A person must review sensitive scenes.

## License

MIT. See `LICENSE`.
