# agentpk

The open source CLI and Python SDK for packaging AI agents.

```
pip install agentpk
```

## Quickstart

```bash
pip install agentpk
```

Both `agentpk` and `agent` are installed. `agentpk` is the canonical form.

```bash
agentpk init my-agent
# edit my-agent/manifest.yaml
agentpk pack my-agent/
```

That's it. You now have a portable `my-agent-0.1.0.agent` file you can
share, deploy, or register.

```bash
# Run it
agentpk run my-agent-0.1.0.agent

# Sign it
agentpk keygen --out my-key.pem
agentpk sign my-agent-0.1.0.agent --key my-key.pem
```

## What is the .agent format?

An `.agent` file is a portable archive containing your agent source code, a
`manifest.yaml` that describes what your agent does and what it needs, and a
`checksums.sha256` file that verifies nothing was tampered with.

The manifest is the important part. It tells runtimes how to start your
agent and tells registries how to list it. One file, two audiences.

## Python SDK

All CLI operations are available as typed Python functions:

```python
from agentpk import pack, analyze, validate, inspect_package, init

# Pack an agent
result = pack("./my-agent", analyze=True)
print(result.trust_score)    # 87
print(result.trust_label)    # "High"
print(result.package_path)   # PosixPath('./dist/my-agent-1.0.0.agent')

# Analyze without packing
analysis = analyze("./my-agent", levels=[1, 2, 3])
print(analysis.discrepancy_count)   # 0

# Validate
val = validate("./my-agent")
print(val.valid)    # True

# Scaffold a new project
r = init("my-node-agent", runtime="nodejs")
print(r.project_dir)   # PosixPath('./my-node-agent')
```

All functions return typed dataclasses. Errors raise typed exceptions
(`AgentpkError`, `ManifestError`, `PackagingError`, `AnalysisError`,
`PackageNotFoundError`) — no `sys.exit()`, no string parsing.

## Multi-language support

agentpk packages agents written in any language. The manifest declares
the runtime; analysis depth depends on the language:

| Language | Analysis | Extractor |
|----------|----------|-----------|
| Python | Full AST | stdlib `ast` module |
| Node.js | Full AST | acorn (via bundled helper) |
| TypeScript | Full AST | @typescript-eslint/parser |
| Go | Pattern-based | Regex on source text |
| Java | Pattern-based | Regex on source text |
| Other | Structural only | Level 2 skipped, reason logged |

Scaffold for any runtime:

```bash
agentpk init my-node-agent --runtime nodejs
agentpk init my-go-agent --runtime go
agentpk init my-java-agent --runtime java
agentpk init my-ts-agent --runtime typescript
```

## Naming convention

Agent names must be lowercase with hyphens and digits only. They must start
with a letter.

| Valid | Invalid |
|-------|---------|
| `fraud-detection` | `Fraud_Detection` |
| `my-agent-2` | `my agent` |
| `data-pipeline` | `data.pipeline` |

## CLI commands

| Command | Description |
|---------|-------------|
| `agentpk init <name>` | Scaffold a new agent project |
| `agentpk pack <dir>` | Pack a directory into a `.agent` file |
| `agentpk validate <target>` | Validate a `.agent` file or project directory |
| `agentpk inspect <file>` | Display metadata and AIR bundle from a `.agent` file |
| `agentpk unpack <file>` | Extract a `.agent` file to a directory |
| `agentpk diff <old> <new>` | Show differences between two `.agent` files |
| `agentpk test` | Run built-in self-tests (22 cases) |
| `agentpk generate [dir]` | Generate a manifest.yaml from code analysis |
| `agentpk list [dir]` | List all `.agent` files in a directory |
| `agentpk run <file>` | Execute a packed `.agent` file as a subprocess |
| `agentpk sign <file>` | Sign a `.agent` file with a private key |
| `agentpk verify <file>` | Verify the signature on a `.agent` file |
| `agentpk keygen` | Generate an Ed25519 key pair for signing |
| `agentpk serve` | Start the REST API and packaging UI |

## REST API and packaging UI

Package and certify agents from a browser or remote system without the CLI:

```bash
pip install agentpk[api]
agentpk serve
# API on http://localhost:8080
# Packaging UI on http://localhost:8080
```

The UI lets you select an agent folder directly from your browser, runs
analysis, and returns a trust score with a download link — no terminal
required. The UI automatically detects whether an LLM API key is
configured and enables or disables Level 3 accordingly.

Via any HTTP client:

```bash
# Submit a packaging job
curl -X POST http://localhost:8080/v1/packages \
     -F "source=@my-agent.agent" \
     -F "analyze=true" \
     -F "levels=1,2,3"

# Poll for completion
curl http://localhost:8080/v1/packages/{job_id}

# Download the .agent file
curl http://localhost:8080/v1/packages/{job_id}/download -o my-agent.agent
```

Options:

```bash
agentpk serve --port 9000
agentpk serve --host 127.0.0.1
agentpk serve --reload          # dev mode
```

## Listing agents

```bash
agentpk list
agentpk list ./agents/
agentpk list ./agents/ --recursive
agentpk list ./agents/ --json
```

## Running agents

```bash
agentpk run my-agent-1.0.0.agent
agentpk run my-agent-1.0.0.agent --dry-run
agentpk run my-agent-1.0.0.agent --keep
agentpk run my-agent-1.0.0.agent --env API_KEY=abc123
agentpk run my-agent-1.0.0.agent -- --flag value
```

The runner extracts the package to a temp directory, validates it, and
launches the entry point using the runtime declared in the manifest.
Extra arguments after `--` are forwarded to the agent process.

| Flag | Effect |
|------|--------|
| `--dry-run` | Validate and extract without executing |
| `--keep` | Keep the temp directory after execution |
| `--env KEY=VALUE` | Set environment variables (repeatable) |

**Warning:** `agent run` executes code from the package. Only run agents
from sources you trust.

## Code analysis and trust scores

agentpk can analyze agent source code and assign a trust score indicating
how well the manifest matches what the code actually does.

See [TRUST.md](TRUST.md) for the full trust score reference and
[docs/agent_analyzer.md](docs/agent_analyzer.md) for the analysis
architecture.

### Generating a manifest from code

```bash
agentpk generate ./my-agent
agentpk generate ./my-agent --level 3
```

The generated manifest includes `# REVIEW` markers on fields that could
not be determined from code analysis alone.

### Packing with analysis

```bash
agentpk pack my-agent/ --analyze
agentpk pack my-agent/ --analyze --level 3
agentpk pack my-agent/ --analyze --level 3 --strict
```

| Flag | Effect |
|------|--------|
| `--analyze` | Run code analysis before packing |
| `--level N` | Analysis depth 1-4 (default: auto) |
| `--strict` | Fail if requested level cannot be reached |
| `--on-discrepancy warn\|fail\|auto` | Discrepancy handling (default: warn) |
| `--memory` | Bundle an AIR memory snapshot with the package |
| `--memory-components` | Comma-separated component list (default: `all`) |

### Analysis levels

| Level | Source | Needs | Weight |
|-------|--------|-------|--------|
| 1 | Structural validation | Nothing | +20 pts |
| 2 | Static analysis (AST or pattern-based) | Nothing | +30 pts |
| 3 | LLM semantic analysis | API key | +25 pts |
| 4 | Runtime sandbox | Container runtime | +25 pts |

Skipped levels subtract points (Level 3 skip: -15, Level 4 skip: -25).
The maximum score is 100 when all four levels pass with no discrepancies.

### Trust score labels

| Score | Label |
|-------|-------|
| 90-100 | Verified |
| 75-89 | High |
| 60-74 | Moderate |
| 40-59 | Low |
| 0-39 | Unverified |

## Portable agent memory (AIR)

Pack an agent with its accumulated intelligence:

```bash
agentpk pack my-agent/ --memory
agentpk pack my-agent/ --analyze --memory
agentpk pack my-agent/ --memory --memory-components fingerprint,trust,org_context
```

The `--memory` flag bundles an AIR (Agent Intelligence Record) snapshot
alongside the package. AIR is an open standard for portable agent memory —
behavioral history, trust trajectory, organizational context, and distilled
insights in platform-agnostic JSON schemas.

The snapshot lives in `_package.air` in the packed manifest and in
`intelligence/` inside the archive. A receiving platform can rehydrate
the agent's behavioral state without rebuilding it from scratch.

Full intelligence export requires `pip install agentpk[memory]`.
Without it, a spec-compliant stub is embedded instead.

See [AIR.md](AIR.md) for the full specification.

## Interactive pack mode

Run `agentpk pack` in a terminal with no flags and the CLI walks you
through environment detection, analysis level selection, and memory
bundling interactively:

```bash
agentpk pack ./my-agent
```

The interactive flow detects available API keys and container runtimes,
presents guided options, shows live progress, and prints a summary with
next steps. It activates automatically in a terminal and is disabled
when piped, when explicit flags are passed (`--analyze`, `--memory`),
or with `--no-interactive`.

## Signing and verification

### Generate a keypair

```bash
agentpk keygen --out my-key.pem
```

Creates two files:
- `my-key.pem` — Ed25519 private key (keep secret, do not commit)
- `my-key.pub.pem` — Ed25519 public key (share with recipients)

### Sign an agent

```bash
agentpk sign fraud-detection-1.0.0.agent --key my-key.pem
agentpk sign fraud-detection-1.0.0.agent --key my-key.pem --signer "Acme AI"
```

Produces `fraud-detection-1.0.0.agent.sig` — a JSON file containing the
manifest hash, Ed25519 signature, algorithm identifier, and optional signer
metadata.

### Verify a signature

```bash
agentpk verify fraud-detection-1.0.0.agent --key my-key.pub.pem
```

## Manifest structure

The manifest has two zones:

**Zone 1 (open core)** — authored by the developer: identity, runtime,
capabilities, permissions, execution settings, and resource requirements.

**Zone 2 (_package)** — generated automatically at pack time: hashes,
timestamps, file counts, and package size. Never edit by hand.

## Validation

```bash
agentpk validate ./my-agent/
agentpk validate my-agent-1.0.0.agent
agentpk validate my-agent-1.0.0.agent --verbose
```

The `--verbose` flag displays a per-stage breakdown. Directories skip
stages 5-6 (checksums and package integrity) since those only apply to
packed files.

## Verifying your installation

```bash
agentpk test
agentpk test --verbose
```

## Examples

Seven valid examples and fourteen intentionally broken examples in `examples/`.

```bash
agentpk pack examples/valid/fraud-detection
agentpk pack examples/valid/fraud-detector-with-memory --memory
agentpk inspect fraud-detector-with-memory-1.0.0.agent
agentpk pack examples/invalid/04-invalid-name
```

The memory examples demonstrate AIR bundling (`fraud-detector-with-memory`,
`healthcare-agent-strict-redaction`) and AIR validation failure modes
(`memory-hash-mismatch`, `memory-missing-component`,
`memory-malformed-air-json`). See `examples/README.md` for the full index.

## Specification

See [SPEC.md](SPEC.md) for the full agent package format specification.

## Development

```bash
pip install -e ".[dev]"
pytest

# With API extras
pip install -e ".[dev,api]"
pytest tests/test_api.py
```

Core dependencies: `click`, `pyyaml`, `pydantic`, `rich`, `cryptography`.
API extras: `fastapi`, `uvicorn`, `python-multipart`.

## About

Built by [Nomotic AI](https://nomotic.ai).

## License

Code: [MIT](LICENSE)
Specification (SPEC.md): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
