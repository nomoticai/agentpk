# agentpk

The open source CLI and Python SDK for packaging AI agents.

```
pip install agentpk
```

## Quickstart

```bash
agent init my-agent
# edit my-agent/manifest.yaml
agent pack my-agent/
```

That's it. You now have a portable `my-agent-0.1.0.agent` file you can
share, deploy, or register.

```bash
# Run it
agent run my-agent-0.1.0.agent

# Sign it
agent keygen --out my-key.pem
agent sign my-agent-0.1.0.agent --key my-key.pem
```

## What is the .agent format?

An `.agent` file is a ZIP archive containing your agent source code, a
`manifest.yaml` that describes what your agent does and what it needs, and a
`checksums.sha256` file that verifies nothing was tampered with. Any tool
that can read ZIP files can open it.

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
agent init my-node-agent --runtime nodejs
agent init my-go-agent --runtime go
agent init my-java-agent --runtime java
agent init my-ts-agent --runtime typescript
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
| `agent init <name>` | Scaffold a new agent project |
| `agent pack <dir>` | Pack a directory into a `.agent` file |
| `agent validate <target>` | Validate a `.agent` file or project directory |
| `agent inspect <file>` | Display metadata from a `.agent` file |
| `agent unpack <file>` | Extract a `.agent` file to a directory |
| `agent diff <old> <new>` | Show differences between two `.agent` files |
| `agent test` | Run built-in self-tests to verify installation |
| `agent generate [dir]` | Generate a manifest.yaml from code analysis |
| `agent list [dir]` | List all `.agent` files in a directory |
| `agent run <file>` | Execute a packed `.agent` file as a subprocess |
| `agent sign <file>` | Sign a `.agent` file with a private key |
| `agent verify <file>` | Verify the signature on a `.agent` file |
| `agent keygen` | Generate an RSA key pair for signing |
| `agent serve` | Start the REST API and packaging UI |

## REST API and packaging UI

Package and certify agents from a browser or remote system without the CLI:

```bash
pip install agentpk[api]
agent serve
# API on http://localhost:8080
# Packaging UI on http://localhost:8080
```

The UI accepts a ZIP of your agent directory, runs analysis, and returns
a trust score with a download link — no terminal required.

Via any HTTP client:

```bash
# Submit a packaging job
curl -X POST http://localhost:8080/v1/packages \
     -F "source=@my-agent.zip" \
     -F "analyze=true" \
     -F "levels=1,2,3"

# Poll for completion
curl http://localhost:8080/v1/packages/{job_id}

# Download the .agent file
curl http://localhost:8080/v1/packages/{job_id}/download -o my-agent.agent
```

Options:

```bash
agent serve --port 9000
agent serve --host 127.0.0.1
agent serve --reload          # dev mode
```

## Listing agents

```bash
agent list
agent list ./agents/
agent list ./agents/ --recursive
agent list ./agents/ --json
```

## Running agents

```bash
agent run my-agent-1.0.0.agent
agent run my-agent-1.0.0.agent --dry-run
agent run my-agent-1.0.0.agent --keep
agent run my-agent-1.0.0.agent --env API_KEY=abc123
agent run my-agent-1.0.0.agent -- --flag value
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
agent generate ./my-agent
agent generate ./my-agent --level 3
```

The generated manifest includes `# REVIEW` markers on fields that could
not be determined from code analysis alone.

### Packing with analysis

```bash
agent pack my-agent/ --analyze
agent pack my-agent/ --analyze --level 3
agent pack my-agent/ --analyze --level 3 --strict
```

| Flag | Effect |
|------|--------|
| `--analyze` | Run code analysis before packing |
| `--level N` | Analysis depth 1-4 (default: auto) |
| `--strict` | Fail if requested level cannot be reached |
| `--on-discrepancy warn\|fail\|auto` | Discrepancy handling (default: warn) |

### Analysis levels

| Level | Source | Needs | Weight |
|-------|--------|-------|--------|
| 1 | Structural validation | Nothing | +20 pts |
| 2 | Static analysis (AST or pattern-based) | Nothing | +30 pts |
| 3 | LLM semantic analysis | API key | +25 pts |
| 4 | Runtime sandbox | Docker | +25 pts |

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

## Signing and verification

### Generate a key pair

```bash
agent keygen --out my-key.pem
```

Creates `my-key.pem` (private key, keep secret) and `my-cert.pem`
(certificate, share with recipients).

### Sign an agent

```bash
agent sign fraud-detection-1.0.0.agent --key my-key.pem
agent sign fraud-detection-1.0.0.agent --key my-key.pem --signer "Acme AI"
```

### Verify a signature

```bash
agent verify fraud-detection-1.0.0.agent --cert my-cert.pem
```

## Manifest structure

The manifest has two zones:

**Zone 1 (open core)** — authored by the developer: identity, runtime,
capabilities, permissions, execution settings, and resource requirements.

**Zone 2 (_package)** — generated automatically at pack time: hashes,
timestamps, file counts, and package size. Never edit by hand.

## Validation

```bash
agent validate ./my-agent/
agent validate my-agent-1.0.0.agent
agent validate my-agent-1.0.0.agent --verbose
```

The `--verbose` flag displays a per-stage breakdown. Directories skip
stages 5-6 (checksums and package integrity) since those only apply to
packed files.

## Verifying your installation

```bash
agent test
agent test --verbose
```

## Examples

Five valid examples and eleven intentionally broken examples in `examples/`.

```bash
agent pack examples/valid/fraud-detection
agent pack examples/invalid/04-invalid-name
```

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
