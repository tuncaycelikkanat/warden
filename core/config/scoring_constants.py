"""Central scoring constants for WARDEN audit calculations.

All magic numbers used in score computations are defined here.
To adjust scoring behavior, modify these constants rather than hunting
through service files.
"""

# ─────────────────────────────────────────────────────────────
# Layer 1 weights (must sum to 1.0 within each group)
# Defined authoritatively in core_group_catalog.py; mirrors here
# for cross-service reference.
# ─────────────────────────────────────────────────────────────

LAYER1_WEIGHT = 0.60
LAYER2_WEIGHT = 0.40

# ─────────────────────────────────────────────────────────────
# Security scoring
# ─────────────────────────────────────────────────────────────

# Semgrep finding penalties (applied per finding)
SEMGREP_ERROR_PENALTY = 40.0       # ERROR severity finding
SEMGREP_WARNING_PENALTY = 10.0     # WARNING severity finding
SEMGREP_INFO_PENALTY = 2.0         # INFO / NOTE severity finding

# Secret leak penalties (applied per unique confirmed secret)
SECRET_LEAK_CONFIRMED_PENALTY = 50.0
SECRET_LEAK_UNVERIFIED_PENALTY = 10.0

# CVE (OSV) penalties
CVE_CRITICAL_PENALTY = 30.0
CVE_HIGH_PENALTY = 15.0
CVE_MEDIUM_PENALTY = 5.0
CVE_LOW_PENALTY = 1.0

# Dependency pinning bonus (all deps pinned → full score)
UNPINNED_DEPENDENCY_PENALTY = 3.0  # per unpinned dep, capped

# ─────────────────────────────────────────────────────────────
# Code complexity scoring
# ─────────────────────────────────────────────────────────────

# Radon cyclomatic complexity rank weights (higher = worse)
COMPLEXITY_RANK_WEIGHTS: dict[str, float] = {
    "A": 0.0,   # CC 1-5   (simple)
    "B": 0.0,   # CC 6-10  (moderate — no penalty)
    "C": 1.0,   # CC 11-15 (complex)
    "D": 2.5,   # CC 16-20 (very complex)
    "E": 4.0,   # CC 21-25 (highly complex)
    "F": 6.0,   # CC > 25  (untestable)
}

COMPLEXITY_PENALTY_PER_UNIT = 3.0   # score points lost per weighted unit

# ─────────────────────────────────────────────────────────────
# Lint / style scoring
# ─────────────────────────────────────────────────────────────

LINT_ERROR_WEIGHT = 2.0         # errors are twice as costly as warnings
LINT_WARNING_WEIGHT = 1.0
LINT_DENSITY_NORMALIZATION = 5.0  # defects per KLOC at which score hits 0

# ─────────────────────────────────────────────────────────────
# Test coverage scoring
# ─────────────────────────────────────────────────────────────

COVERAGE_TARGET_PCT = 80.0      # 80% → full score; <40% → zero
COVERAGE_ZERO_THRESHOLD = 40.0  # below this = 0 score

# ─────────────────────────────────────────────────────────────
# Resilience scoring
# ─────────────────────────────────────────────────────────────

# Density (defects per file) at which score reaches 0
RESILIENCE_DEFECT_DENSITY_THRESHOLD = 0.4

# Severity multipliers (HIGH, MEDIUM, LOW)
RESILIENCE_SEVERITY_WEIGHTS: dict[str, float] = {
    "HIGH": 2.0,
    "MEDIUM": 1.0,
    "LOW": 0.5,
}

# ─────────────────────────────────────────────────────────────
# Technical debt scoring
# ─────────────────────────────────────────────────────────────

HOTSPOT_CHURN_RATIO_THRESHOLD = 0.05   # 5% churn → considered hot
HOTSPOT_PENALTY_MULTIPLIER = 40.0      # penalty = churn_ratio * multiplier
TODO_PENALTY_PER_MARKER = 0.2          # score lost per TODO/FIXME
MAX_TODO_PENALTY = 10.0                # cap: at most 10 points from TODOs

# ─────────────────────────────────────────────────────────────
# Duplication scoring
# ─────────────────────────────────────────────────────────────

DUPLICATION_ZERO_PCT = 25.0    # 25%+ duplication → score 0
DUPLICATION_FULL_PCT = 3.0     # ≤3% duplication → full score

# ─────────────────────────────────────────────────────────────
# Documentation scoring
# ─────────────────────────────────────────────────────────────

DOCSTRING_TARGET_PCT = 80.0   # 80%+ docstring coverage → full score
DOCSTRING_ZERO_PCT = 20.0     # <20% → score 0

# ─────────────────────────────────────────────────────────────
# Grading thresholds (Layer 1 + total score)
# ─────────────────────────────────────────────────────────────

GRADE_THRESHOLDS: dict[str, int] = {
    "A+": 95,
    "A":  85,
    "B":  70,
    "C":  55,
    "D":  40,
    # Below D → F
}
