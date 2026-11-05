# Screenplay Promo Finder (`promofinder`)

A reproducible, verifiable CLI-driven pipeline for identifying, validating, and ranking short-form promotional video cuts from serialized screenplay scripts.

---

## 1. System Overview

`promofinder` parses screenplay timelines into structured events and evaluates candidate promotional cuts for short-form platforms (Instagram Reels, TikTok, YouTube Shorts). Every candidate must satisfy strict structural and temporal invariants before ranking:

1. **Duration Compliance**: Promo cut duration must satisfy `20.0 <= duration <= 60.0` seconds (editorial sweet spot: `30.0 <= duration <= 45.0` seconds).
2. **Hook Delivery**: A compelling opening dialogue beat must start within 3.0 seconds (`0 <= hook_offset_ms <= 3000`) and fully complete within 3.0 seconds (`0 <= hook_complete_by_ms <= 3000`).
3. **Dialogue Boundary Integrity**: Cuts must never bisect active spoken dialogue. Both start and end cut timestamps snap to exact speech boundaries (`boundary_conflicts == 0`).
4. **Terminal Cliffhanger**: Cuts must terminate on an acute, unresolved dramatic question or impending confrontation within 3.0 seconds of the cut end (`cliff_gap_ms <= 3000`) with zero resolving dialogue beats after the cliffhanger inside the cut (`answer_events_after_cliff == 0`).
5. **Deterministic Lexicographic Ranking**: Promos are ranked strictly using observable structural properties (hook completion speed, acute cliffhanger proximity, sweet-spot duration, dialogue density) without subjective human ratings or artificial score curves.

> **Evaluation Disclosure**: Viewer engagement, retention, CTR, and cold-viewer comprehension were not empirically measured on live audiences. The tool enforces deterministic timing boundaries and lexical pattern proxies.

---

## 2. Model & Execution Disclosure

- **Runtime Mode**: Fully local deterministic rule baseline with regex-assisted lexical classification.
- **External Model Calls**: **0** external API requests during automated discovery.
- **API Cost**: **$0.00 USD**.
- **Execution Speed**: Fully local, sub-second parsing and candidate evaluation.
- **LLM Extension**: Includes an extensible `BaseProvider` and `ManualProvider` for offline prompt review and batch model integration without leaking private screenplay text.

---

## 3. Installation

The core `promofinder` package runs entirely on the **Python standard library** (Python 3.10+).

```bash
# Clone the repository
git clone https://github.com/WaqarMoid/promofinder-problem1.git
cd promofinder-problem1

# (Optional) Create and activate a virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install test and verification dependencies (pytest, pymupdf, python-docx)
pip install -r requirements.txt
```

---

## 4. Pipeline Execution & Synthetic Quickstart

The package exposes a unified CLI with four pipeline stages:

```bash
# 1. Ingest screenplay files and serialize timed dialogue/action events
python -m promofinder ingest --input sample_input --run runs/demo_run

# 2. Discover and mechanically validate candidate cuts across episodes
python -m promofinder analyze --run runs/demo_run --provider baseline

# 3. Deduplicate overlapping windows, rank lexicographically, and package exports
python -m promofinder finalize --run runs/demo_run --top-k 10

# 4. Perform independent release audit and output canonical run_facts.json
python -m promofinder evaluate --run runs/demo_run
```

Running the pipeline on `sample_input/` processes the synthetic screenplay (`episode-001.txt`) and deterministically discovers 1 valid promotional cut (`00:00.00 - 00:32.00`, 32.0s, hook complete at 2.50s, terminal cliffhanger at 00:28.00).

### Generated Artifacts in `runs/<run_id>/`:
- `manifest.json`: Full episode metadata, durations, and source hashes.
- `events.json` / `events.jsonl`: Serialized timeline events with exact hundredths timestamps.
- `candidates.jsonl`: Mechanically valid candidate proposals accepted by downstream validation.
- `rejected.jsonl` and `rejected/`: Records of rejected proposals and disqualification reasons.
- `episode_analyses.jsonl` and `raw/`: Per-episode analysis records including explicit `no_candidate` reasons.
- `exports/ranked_all_candidates.json` & `.csv`: All deduplicated valid candidates ranked lexicographically.
- `exports/top10_diverse_promos.json` & `.csv`: Top 10 diverse promos spanning unique episodes and themes.
- `exports/top3_first_to_post.json`: Top 3 First-to-Post promotional cuts with narrative evidence and tradeoffs.
- `run_facts.json`: Authoritative machine-readable metrics, coverage, and yield data.
- `report.html`: Self-contained interactive inspection report.

---

## 5. Automated Test Suite

### Public-Only Mode (Out-of-the-Box)
Run the automated test suite without private screenplays:

```bash
python -m unittest discover -s tests -v
```

- **Discovered**: 20 tests.
- **Passing**: 15 tests (adversarial edge cases, duration boundaries, hook timing, CSV sanitization, synthetic end-to-end run).
- **Skipped**: 5 tests (cleanly skipped with explanatory messages because the private full screenplay pack is absent).

### Evaluator Mode (With Full Screenplay Pack & Canonical Run)
For evaluators with access to the private screenplay collection and canonical run:

```bash
# On Linux / macOS:
export PROMOFINDER_SCREENPLAYS_DIR="/path/to/screenplays"
export PROMOFINDER_INVENTORY_PATH="/path/to/inventory.json"
export PROMOFINDER_CANONICAL_RUN="/path/to/runs/canonical_run"

# On Windows (PowerShell):
$env:PROMOFINDER_SCREENPLAYS_DIR="D:\path\to\screenplays"
$env:PROMOFINDER_INVENTORY_PATH="D:\path\to\inventory.json"
$env:PROMOFINDER_CANONICAL_RUN="D:\path\to\runs\canonical_run"

python -m unittest discover -s tests -v
```

- **Discovered & Passing**: **34 / 34 tests passing** with zero failures and zero errors.

---

## 6. Candidate Accounting & Invariants Clarification

- **Proposal Validation Accounting**: In the full 50-episode run, the discovery engine emits candidate proposals that are subjected to downstream mechanical validation. Exactly 111 proposals satisfy all mechanical gates (`111 / 111 = 100.0%`). This measures proposal acceptance post-discovery; raw temporal windows failing opening hook or cliffhanger thresholds are rejected prior to downstream validation or recorded in `rejected/`.
- **Coverage & Yield**:
  - Processing Coverage: `(45 success + 5 no_candidate) / 50 = 100.0%`.
  - Candidate Yield: `45 / 50 = 90.0%`.

---

## 7. Architecture & Code Structure

```
promofinder/
├── __init__.py      # Package initialization and version
├── __main__.py      # CLI entry point (`python -m promofinder`)
├── cli.py           # Command-line interface definition and argument parsing
├── config.py        # Pipeline parameters, duration limits, and editorial thresholds
├── evaluate.py      # Independent evaluation, metrics aggregation, and run_facts generation
├── export.py        # Export generation (CSV, JSON, HTML report, failure audits)
├── models.py        # Data models, contracts, and timestamp converters
├── parser.py        # Screenplay ingestion, tokenization, and regression handling
├── pipeline.py      # Pipeline orchestration and processing loops
├── provider.py      # Candidate discovery providers (Deterministic baseline & Manual review)
├── rank.py          # Deduplication, lexicographic ranking, and diversity selection
└── validate.py      # Hard mechanical eligibility validation and boundary enforcement

sample_input/
└── episode-001.txt  # Synthetic demonstration screenplay with timed beats

tests/
├── test_adversarial_fixtures.py     # Predeclared adversarial edge cases
├── test_synthetic_edge_cases.py     # Boundary timing (19.99s vs 20.00s, 2.99s vs 3.01s, etc.)
├── test_reconciliation_gates.py     # Cross-file arithmetic and observable field assertions
├── test_release_audit.py            # Independent release audit of raw run artifacts
├── test_discovery.py                # Candidate validation contracts
└── test_parser.py                   # Parser fidelity, timestamp accuracy, and event counts
```

---

## 8. License

Distributed under the MIT License. See `LICENSE` for details.
