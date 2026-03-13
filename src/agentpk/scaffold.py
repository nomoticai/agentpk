"""Project scaffolding for ``agent init``."""

from __future__ import annotations

from pathlib import Path

from agentpk.constants import FORMAT_VERSION

# ---------------------------------------------------------------------------
# Template content
# ---------------------------------------------------------------------------

_MANIFEST_TEMPLATE = """\
# ──────────────────────────────────────────────────────────────────────────
# Agent Package Manifest  (spec_version {spec_version})
#
# This file describes your agent so that runtimes, registries, and
# package managers can understand what it does, what it needs, and
# how to run it.
#
# Two zones:
#   Zone 1 (open core)  — identity, runtime, capabilities, execution
#   Zone 2 (_package)   — auto-generated at pack time — do not edit
# ──────────────────────────────────────────────────────────────────────────

spec_version: "{spec_version}"

# ── Identity ──────────────────────────────────────────────────────────────
# name:         lowercase, hyphens and numbers only  (e.g. my-agent)
# version:      semantic version  (MAJOR.MINOR.PATCH)
# description:  one-line summary shown in registries

name: {name}
version: "0.1.0"
description: "TODO: Describe what this agent does."
# display_name: "{display_name}"
# author: "Your Name"
# organization: "Your Org"
# license: "MIT"
# tags:
#   - example

# ── Runtime ───────────────────────────────────────────────────────────────
# language:         python | nodejs | typescript | go | rust
# language_version: minimum required version
# entry_point:      path to the file that contains the agent entry function
# entry_function:   function name to call (default: main)
# dependencies:     path to dependency file (e.g. requirements.txt)

runtime:
  language: python
  language_version: "3.11"
  entry_point: src/agent.py
  entry_function: main
  dependencies: requirements.txt

# ── Model (optional) ─────────────────────────────────────────────────────
# Set agnostic: true if your agent works with any LLM.
#
# model:
#   agnostic: true
#   preferred: "claude-sonnet-4-20250514"
#   minimum_context: 16000
#   alternatives:
#     - "gpt-4o"

# ── Framework (optional) ─────────────────────────────────────────────────
# Declare which agent framework you use.
# Valid names: langchain, crewai, autogen, llamaindex, haystack,
#              semantic-kernel, dspy, smolagents, pydantic-ai, custom
#
# framework:
#   name: custom
#   version: "1.0"

# ── Capabilities ──────────────────────────────────────────────────────────
# List every tool your agent exposes.
#   id:          unique identifier
#   scope:       read | write | execute | delete | admin
#   required:    true if the runtime must provide this tool
#   targets:     optional list of resource patterns
#   constraints: optional dict of tool-specific limits

capabilities:
  tools: []
  # - id: example-tool
  #   description: "What this tool does."
  #   scope: read
  #   required: true
  #   targets:
  #     - "resource.*"

# ── Permissions (optional) ────────────────────────────────────────────────
# permissions:
#   data_classes:
#     - name: pii
#       access: read
#   environments:
#     allowed: [API_KEY]
#     denied: [SECRET_TOKEN]

# ── Execution ─────────────────────────────────────────────────────────────
# type:  scheduled | triggered | continuous | on-demand
#
# For "scheduled": set schedule (cron expression) and timezone.
# For "triggered": set triggers list.

execution:
  type: on-demand
  # schedule: "0 */6 * * *"
  # timezone: "UTC"
  # triggers:
  #   - event: some_event
  # timeout_minutes: 30
  # max_concurrent_instances: 1
  # retry:
  #   max_attempts: 3
  #   backoff_seconds: 60

# ── Resources (optional) ─────────────────────────────────────────────────
# resources:
#   memory_mb: 512
#   cpu_shares: 256
#   network: none          # none | inbound | outbound-only | bidirectional

"""

_AGENT_PY = """\
\"\"\"Agent entry point.

This is the file referenced by runtime.entry_point in manifest.yaml.
The function referenced by runtime.entry_function (default: main) is
called by the agent runtime to start your agent.
\"\"\"


def main() -> None:
    \"\"\"Run the agent.\"\"\"
    # TODO: implement your agent logic here
    print("Hello from {name}!")


if __name__ == "__main__":
    main()
"""

_INIT_PY = """\
\"\"\"Agent source package.\"\"\"
"""

_REQUIREMENTS = """\
# Add your agent's Python dependencies here, one per line.
# Example:
# requests>=2.28
# pydantic>=2.0
"""

_README = """\
# {name}

TODO: Describe your agent.

## Quick start

```bash
# Pack into a .agent file
agent pack .

# Validate the package
agent validate {name}-0.1.0.agent
```
"""

_GITIGNORE = """\
*.agent
__pycache__/
*.py[cod]
.venv/
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scaffold(project_name: str, output_dir: Path) -> list[str]:
    """Create a new agent project at *output_dir* / *project_name*.

    Returns a list of created file paths (relative to the project root).
    """
    project_dir = output_dir / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "src").mkdir(exist_ok=True)

    display_name = project_name.replace("-", " ").title()

    files_created: list[str] = []

    def _write(rel: str, content: str) -> None:
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        files_created.append(rel)

    _write(
        "manifest.yaml",
        _MANIFEST_TEMPLATE.format(
            spec_version=FORMAT_VERSION,
            name=project_name,
            display_name=display_name,
        ),
    )
    _write("src/__init__.py", _INIT_PY)
    _write("src/agent.py", _AGENT_PY.format(name=project_name))
    _write("requirements.txt", _REQUIREMENTS)
    _write("README.md", _README.format(name=project_name))
    _write(".gitignore", _GITIGNORE)

    return files_created
