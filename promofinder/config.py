"""
Configuration for promofinder package.
Loads from optional config.json or provides verified defaults.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Optional

# Root workspace directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Screenplay source directory (default for CLI when not specified)
SCRIPTS_DIR = BASE_DIR / "sample_input"

# Temporal bounds (seconds)
MIN_PROMO_DURATION = 20.0
MAX_PROMO_DURATION = 60.0
HOOK_MAX_WINDOW = 3.0
SWEET_SPOT_DURATION_MIN = 30.0
SWEET_SPOT_DURATION_MAX = 45.0

# Editorial limits
MAX_CANDIDATES_PER_EPISODE = 3
TOP_N_DIVERSE = 10
FIRST_TO_POST_COUNT = 3


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads configuration overrides from JSON if present."""
    default_cfg = {
        "bounds": {
            "min_duration_seconds": MIN_PROMO_DURATION,
            "max_duration_seconds": MAX_PROMO_DURATION,
            "hook_max_seconds": HOOK_MAX_WINDOW,
            "sweet_spot_min_seconds": SWEET_SPOT_DURATION_MIN,
            "sweet_spot_max_seconds": SWEET_SPOT_DURATION_MAX,
        },
        "export_limits": {
            "max_candidates_per_episode": MAX_CANDIDATES_PER_EPISODE,
            "top_k_diverse": TOP_N_DIVERSE,
            "first_to_post_count": FIRST_TO_POST_COUNT,
        },
    }
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            overrides = json.load(f)
            if "bounds" in overrides:
                default_cfg["bounds"].update(overrides["bounds"])
            if "export_limits" in overrides:
                default_cfg["export_limits"].update(overrides["export_limits"])
    return default_cfg
