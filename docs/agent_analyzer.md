# Agent Analyzer and Trust Score Architecture

The agent analyzer is a multi-level code analysis system that examines agent
source code and assigns a trust score indicating how well the manifest matches
what the code actually does.

## Overview

The analyzer provides two modes:

- **Verify mode** (`agent pack --analyze`): Compares an existing manifest
  against what the code actually does. Embeds the trust score in the package.
- **Generate mode** (`agent generate`): Produces a manifest from scratch by
  analyzing the code. Fields that cannot be determined automatically are marked
  with `# REVIEW` comments.

## Analysis Levels

Four independent evidence sources, each optional and carrying a score weight.
Levels are cumulative evidence, not a strict prerequisite chain.

### Level 1 -- Structural Validation

- **What:** Validates manifest schema, required fields, enum values using the
  existing 6-stage validation pipeline.
- **Needs:** Nothing (always runs if a manifest is present).
- **Weight:** +20 points if passed.
- **Skip penalty:** -10 points if no manifest is present.

### Level 2 -- Static AST Analysis

- **What:** Walks all source files and extracts behavioral signals via AST
  analysis. Detects imports, network operations, file I/O, subprocess calls,
  environment variable access, and known tool framework registrations.
- **Needs:** Nothing (pure Python `ast` module, no external dependencies).
- **Weight:** +30 points if passed, partial if discrepancies found.
- **Skip penalty:** -20 points if skipped.

For Python files, the analyzer uses the `ast` module to detect:

| Signal | Detection Pattern |
|--------|-------------------|
| Imports | `ast.Import`, `ast.ImportFrom` |
| Network calls | `requests.*`, `httpx.*`, `urllib.request.*`, `aiohttp.*` |
| LLM clients | `openai.*`, `anthropic.*`, `langchain_openai.*` |
| File I/O | `open()`, `Path.write_text()`, `Path.read_text()` |
| Subprocess | `subprocess.run()`, `os.system()`, `os.popen()` |
| Env vars | `os.environ.get()`, `os.getenv()`, `os.environ[]` |
| Tool registrations | `@tool`, `Tool()`, `StructuredTool()`, `BaseTool` subclasses |
| Entry functions | `main()`, `run()`, `execute()`, `invoke()`, `handler()` |

For Node.js/TypeScript files, regex-based analysis detects similar patterns:
`require()`, `fetch()`, `axios.*`, `fs.*`, `child_process`, `process.env.*`.

After extraction, findings are compared against the manifest:

- Network calls without declared tools: **MAJOR** discrepancy
- Network writes with only read-scope tools: **CRITICAL** discrepancy
- Tool registrations not in manifest: **MAJOR** discrepancy
- Manifest tools not found in code: **MINOR** discrepancy
- Subprocess calls without execute-scope tools: **MAJOR** discrepancy
- Database imports without `data_class` declarations: **MAJOR** discrepancy

### Level 3 -- LLM Semantic Analysis

- **What:** Sends source files to an LLM and asks it to generate what the
  manifest SHOULD say, with specific file:line citations. Compares LLM findings
  against the existing manifest and Level 2 static findings.
- **Needs:** `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in environment.
- **Weight:** +25 points if confirmed, partial if discrepancies found.
- **Skip penalty:** -15 points if no API key available.

Provider selection:
1. `ANTHROPIC_API_KEY` present: uses `claude-haiku-4-5-20251001`
2. `OPENAI_API_KEY` present: uses `gpt-4o-mini`
3. Neither: level skipped

LLM findings without code citations are weighted at 50% of their penalty.
Findings confirmed by both static analysis and LLM are high confidence.

No LLM SDK dependency is required. API calls use `urllib.request` directly.

### Level 4 -- Runtime Sandbox

- **What:** Executes the agent in an isolated Docker container. Intercepts
  network calls, file writes, subprocess executions, and env var reads.
  Compares observed behavior against manifest declarations.
- **Needs:** Docker installed and running.
- **Weight:** +25 points if confirmed, partial if discrepancies found.
- **Skip penalty:** -25 points if Docker not available.

Sandbox approach:
1. Build a minimal Docker image with the agent's runtime and dependencies.
2. Run with `--network=none` and `--read-only` for isolation.
3. Collect stdout/stderr for behavioral signals.
4. Compare observations against manifest declarations.
5. Tear down container and remove image.

The sandbox is best-effort: even import-time behavior provides useful signals.
Agents that fail due to missing external data are expected -- the analyzer
examines what was attempted before the failure.

## Score Calculation

```
base = 0

# Each level contributes if run
if level1_ran: base += level1_score   # 0-20
if level2_ran: base += level2_score   # 0-30
if level3_ran: base += level3_score   # 0-25
if level4_ran: base += level4_score   # 0-25

# Penalties for skipped levels
if not level1_ran: base -= 10
if not level2_ran: base -= 20
if not level3_ran: base -= 15
if not level4_ran: base -= 25

# Floor at 0
trust_score = max(0, base)
```

Discrepancies reduce the score of the level that found them:

| Severity | Penalty | Example |
|----------|---------|---------|
| Minor | -5 per item | Declared tool not found in code |
| Major | -10 per item | Code uses network but no tool declared |
| Critical | -20 per item | Declared read scope but code does write |

## Trust Score Interpretation

| Score | Label | Meaning |
|-------|-------|---------|
| 90-100 | Verified | All available levels passed, no discrepancies |
| 75-89 | High | Most levels passed, minor gaps |
| 60-74 | Moderate | Partial analysis, some discrepancies or skipped levels |
| 40-59 | Low | Limited analysis or significant discrepancies |
| 0-39 | Unverified | Minimal analysis performed |

## Commands

### `agent generate`

```bash
agent generate [DIRECTORY] [--level N] [--output PATH] [--force]
```

Analyzes source code and produces a `manifest.yaml`. Fields that cannot be
determined from code are marked with `# REVIEW` comments.

If `manifest.yaml` already exists, the command errors unless `--force` is set.

### `agent pack --analyze`

```bash
agent pack <DIR> --analyze [--level N] [--strict] [--on-discrepancy warn|fail|auto]
```

Runs code analysis, displays results, and embeds the trust score in the
`_package` block of the packed manifest.

| Flag | Default | Effect |
|------|---------|--------|
| `--analyze` | off | Enable code analysis |
| `--level N` | auto | Maximum analysis level (1-4) |
| `--strict` | off | Fail if requested level cannot be reached |
| `--on-discrepancy` | warn | `warn`: show warnings; `fail`: abort; `auto`: attempt fix |

When `--level` is not specified, the tool auto-detects the highest available
level based on environment (API key present? Docker running?).

### `agent inspect` (trust score display)

When a package contains an analysis block, `agent inspect` displays the trust
score alongside other metadata:

```
                 Trust Score
+-------------------------------------------+
| score          | 82/100  (High)           |
| levels run     | 1, 2, 3                  |
| levels skipped | 4  (Docker not available)|
| discrepancies  | none                     |
| analyzed at    | 2026-03-12T23:44:45Z     |
| llm provider   | anthropic/claude-haiku.. |
+-------------------------------------------+
```

Packages without analysis display "unverified (no analysis performed)."

## Package Metadata

When `--analyze` is used, the `_package` block includes an `analysis` key:

```yaml
_package:
  format: agent-package-format
  format_version: "1.0"
  packaged_at: 2026-03-12T23:44:48Z
  packaged_by: agentpk/0.1.0
  manifest_hash: sha256:2ddf5591...
  files_hash: sha256:f28a3dd2...
  total_files: 4
  package_size_bytes: 2458
  analysis:
    level_requested: 3
    levels_run: [1, 2, 3]
    levels_skipped:
      - level: 4
        reason: Docker not available
    trust_score: 82
    trust_label: High
    discrepancies: []
    analyzed_at: 2026-03-12T23:44:45Z
    llm_provider: anthropic/claude-haiku-4-5-20251001
    static_findings_summary:
      imports_detected: 4
      network_calls: 2
      tool_registrations: 3
      undeclared_capabilities: 0
```

When `--analyze` is NOT used, the `analysis` key is absent entirely. A
receiver seeing no analysis block knows the package was not analyzed.

## Discrepancy Types

| Type | Code | Meaning |
|------|------|---------|
| Undeclared | `undeclared` | Found in code, not declared in manifest |
| Unconfirmed | `unconfirmed` | Declared in manifest, not found in code |
| Scope mismatch | `scope_mismatch` | Declared scope doesn't match code behavior |

## Module Structure

- `src/agentpk/analyzer.py` -- Core analysis engine with all four levels
- `src/agentpk/constants.py` -- Trust score weights, penalties, and label thresholds
- `src/agentpk/cli.py` -- `generate` command and `pack --analyze` integration
- `tests/test_analyzer.py` -- 34 tests covering all levels, scoring, and CLI

## Dependencies

Level 1 and 2 require no external dependencies beyond the Python stdlib.
Level 3 uses `urllib.request` to call LLM APIs (no SDK required).
Level 4 requires Docker to be installed and accessible via `docker` CLI.

The `openai` and `anthropic` Python packages are NOT required as dependencies.
