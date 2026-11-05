# Screenplay Promo Finder (`promofinder`)

A reproducible, verifiable CLI-driven pipeline for identifying, validating, and ranking high-converting vertical video promo cuts (20–60s) directly from serialized screenplay scripts.

---

## 1. System Overview

`promofinder` analyzes screenplay timelines to extract promotional cuts designed for short-form video platforms (TikTok, Instagram Reels, YouTube Shorts). Every candidate must satisfy strict structural, acoustic, and narrative invariants before ranking:

1. **Duration Compliance**: Promo cut duration must be strictly between 20.0 and 60.0 seconds (sweet spot 30.0–45.0s).
2. **Hook Delivery**: A compelling opening dialogue beat must start within 3.0 seconds (`hook_offset_ms <= 3000`) and fully complete within 3.0 seconds (`hook_complete_by_ms <= 3000`).
3. **Dialogue Integrity**: Cuts must never bisect active dialogue. All start and end boundaries snap to exact speech start/end boundaries (`zero_speech_bisection = True`).
4. **Terminal Cliffhanger**: Cuts must terminate on an acute, unresolved dramatic question or impending threat without resolving beats inside the window (`cliff_gap_ms <= 3000`).
5. **Deterministic Lexicographic Ranking**: Promos are ranked strictly on observable structural and lexical heuristics with zero subjective human-assigned ratings or artificial score curves.

---

## 2. Model & Execution Disclosure

- **Runtime Mode**: Deterministic rule baseline with regex-assisted lexical classification.
- **External Model Calls**: **0** external API requests during automated discovery.
- **API Cost**: **$0.00**.
- **Execution Speed**: Fully local, sub-second parsing and candidate evaluation.
- **LLM Extension**: The codebase includes an extensible `BaseProvider` and `ManualProvider` for offline review and batch LLM prompts without leaking private screenplay data.

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

# Install test dependencies (pytest, pymupdf, python-docx)
pip install -r requirements.txt
```

---

## 4. Pipeline Execution & Quickstart

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

### Generated Artifacts in `runs/<run_id>/`:
- `manifest.json`: Full episode metadata, durations, and source hashes.
- `events.jsonl`: Serialized timeline events with exact hundredths timestamps.
- `candidates.jsonl`: Mechanically valid candidate promo cuts with observable fields.
- `rejections.jsonl`: Traceable audit records for rejected windows and non-qualifying episodes.
- `exports/top10_diverse_promos.json` & `.csv`: Top diverse candidates across themes and episodes.
- `top3_delivery.json`: First-to-Post promotional cuts ready for video assembly.
- `run_facts.json`: Authoritative machine-readable metrics, coverage, and yield data.
- `report.html`: Self-contained interactive inspection report.

---

## 5. Automated Test Suite

Run the full automated test suite containing synthetic edge cases, boundary assertions, and adversarial fixtures:

```bash
python -m unittest discover -s tests -v
```

All synthetic fixtures and adversarial tests execute and pass out-of-the-box without requiring private screenplay packs.

### For Evaluators with Full Screenplay Packs:
To run the full suite against a private screenplay collection and canonical run:
```bash
# Set environment variables pointing to local private directories:
export PROMOFINDER_SCREENPLAYS_DIR="/path/to/screenplays"
export PROMOFINDER_CANONICAL_RUN="/path/to/canonical_run"

python -m unittest discover -s tests -v
```

---

## 6. Architecture & Code Structure

```
promofinder/
├── __init__.py      # Package initialization and version
├── __main__.py      # CLI entry point (`python -m promofinder`)
├── cli.py           # Command-line interface definition and argument parsing
├── config.py        # Pipeline parameters, duration limits, and editorial thresholds
├── evaluate.py      # Independent evaluation, metrics aggregation, and run_facts generation
├── export.py        # Export generation (CSV, JSON, HTML report, failure audits)
├── models.py        # Pydantic/dataclass data models, contracts, and timestamp converters
├── parser.py        # Screenplay ingestion, regex tokenization, and regression handling
├── pipeline.py      # End-to-end orchestration and candidate processing loops
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

## 7. License

Distributed under the MIT License. See `LICENSE` for details.
