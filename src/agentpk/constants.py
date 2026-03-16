"""Constants for the agentpk package format."""

FORMAT_VERSION = "1.0"
SPEC_VERSION = "1.0"

AGENT_EXTENSION = ".agent"

MANIFEST_FILENAME = "manifest.yaml"
CHECKSUMS_FILENAME = "checksums.sha256"

RESERVED_FILENAMES = [
    MANIFEST_FILENAME,
    CHECKSUMS_FILENAME,
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    ".agentignore",
    ".agentrc",
    "SPEC.md",
]

VALID_LANGUAGES = ["python", "nodejs", "typescript", "go", "rust", "java"]

# Languages with full AST-based extraction (highest Level 2 accuracy)
SUPPORTED_LANGUAGES = ["python", "nodejs", "typescript", "go", "java"]
AST_LANGUAGES = ["python", "nodejs", "typescript"]

# Languages with pattern-based extraction (good accuracy, deterministic)
PATTERN_LANGUAGES = ["go", "java"]

VALID_EXECUTION_TYPES = ["scheduled", "triggered", "continuous", "on-demand"]

VALID_SCOPES = ["read", "write", "execute", "delete", "admin"]

VALID_NETWORK = ["none", "inbound", "outbound-only", "bidirectional"]

VALID_FRAMEWORKS = [
    "langchain",
    "crewai",
    "autogen",
    "llamaindex",
    "haystack",
    "semantic-kernel",
    "dspy",
    "smolagents",
    "pydantic-ai",
    "custom",
]

# ---------------------------------------------------------------------------
# Trust score weights and thresholds
# ---------------------------------------------------------------------------

LEVEL_WEIGHTS: dict[int, int] = {1: 20, 2: 30, 3: 25, 4: 25}
LEVEL_SKIP_PENALTIES: dict[int, int] = {1: -10, 2: -20, 3: -15, 4: -25}

DISCREPANCY_PENALTIES: dict[str, int] = {
    "minor": -5,
    "major": -10,
    "critical": -20,
}

TRUST_LABELS: list[tuple[int, str]] = [
    (90, "Verified"),
    (75, "High"),
    (60, "Moderate"),
    (40, "Low"),
    (0, "Unverified"),
]


def trust_label(score: int) -> str:
    """Return human-readable trust label for *score*."""
    for threshold, label in TRUST_LABELS:
        if score >= threshold:
            return label
    return "Unverified"

