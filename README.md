# agentpk

The open source CLI for packaging AI agents.

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

## Listing agents

Scan a directory for `.agent` files and display a summary table:

```bash
agent list
agent list ./agents/
agent list ./agents/ --recursive
agent list ./agents/ --json
```

`--recursive` walks subdirectories. `--json` prints machine-readable JSON
instead of a Rich table. Invalid `.agent` files are included in the listing
with a warning rather than causing the command to fail.

## Running agents

Execute a packed `.agent` file as a subprocess:

```bash
agent run my-agent-1.0.0.agent
agent run my-agent-1.0.0.agent --dry-run
agent run my-agent-1.0.0.agent --keep
agent run my-agent-1.0.0.agent --env API_KEY=abc123
agent run my-agent-1.0.0.agent -- --flag value
```

The runner extracts the package to a temp directory, validates it, and
launches the entry point using the runtime declared in the manifest
(Python, Node.js, or TypeScript). Extra arguments after `--` are forwarded
to the agent process.

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

See [docs/agent_analyzer.md](docs/agent_analyzer.md) for the full
architecture documentation.

### Generating a manifest from code

If you have agent source code but no `manifest.yaml`, generate one:

```bash
agent generate ./my-agent
agent generate ./my-agent --level 3
```

The generated manifest includes `# REVIEW` markers on fields that could
not be determined from code analysis alone (display name, author, etc.).

### Packing with analysis

Add `--analyze` to `agent pack` to run code analysis and embed a trust
score in the package:

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
| 2 | Static AST analysis | Nothing | +30 pts |
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

When you inspect a package, the trust score is displayed. Packages without
analysis show "unverified."

## Signing and verification

agentpk includes built-in cryptographic signing so recipients can verify
that a `.agent` file was produced by a trusted party and has not been
modified.

### Generate a key pair

```bash
agent keygen --out my-key.pem
```

This creates two files:

- `my-key.pem` -- RSA-2048 private key (keep secret)
- `my-cert.pem` -- self-signed X.509 certificate (share with recipients)

### Sign an agent

```bash
agent sign fraud-detection-1.0.0.agent --key my-key.pem
agent sign fraud-detection-1.0.0.agent --key my-key.pem --signer "Acme AI"
```

This produces a `.sig` file alongside the `.agent` file (e.g.
`fraud-detection-1.0.0.agent.sig`). The `.sig` file is JSON containing the
manifest hash, an RSA-PSS-SHA256 signature, and optional signer metadata.

### Verify a signature

```bash
agent verify fraud-detection-1.0.0.agent --cert my-cert.pem
```

Verification re-computes the manifest hash, compares it to the value in the
`.sig` file, and cryptographically verifies the signature against the
certificate. If the agent or signature has been tampered with, verification
fails.

## Manifest structure

The manifest has two zones:

**Zone 1 (open core)** contains everything a runtime needs: identity fields
(name, version, description), runtime configuration (language, entry point,
dependencies), capabilities (tools your agent exposes), execution settings
(scheduled, triggered, or on-demand), and resource requirements.

**Zone 2 (_package)** is generated automatically at pack time. It contains
hashes, timestamps, file counts, and package size. Never edit this zone by
hand.

## Validation

Validate a project directory or packed `.agent` file against the 6-stage
validation pipeline:

```bash
agent validate ./my-agent/
agent validate my-agent-1.0.0.agent
agent validate my-agent-1.0.0.agent --verbose
```

The `--verbose` flag displays a per-stage breakdown showing which stages
passed, failed, or were skipped. Directories skip stages 5-6 (checksums
and package integrity) since those only apply to packed files.

## Verifying Your Installation

Run the built-in self-test suite to confirm agentpk is working correctly:

```bash
agent test
```

This generates 14 temporary agent fixtures (4 valid, 10 invalid), runs the
validation pipeline against each one, and reports pass/fail results. Add
`--verbose` for per-test detail:

```bash
agent test --verbose
```

## Examples

Five valid examples and eleven intentionally broken examples are included
in `examples/`. See [examples/README.md](examples/README.md) for the full
table.

```bash
# Pack a valid example
agent pack examples/valid/fraud-detection

# Confirm an invalid example is correctly rejected
agent pack examples/invalid/04-invalid-name
```

## Specification

See [SPEC.md](SPEC.md) for the full agent package format specification.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Dependencies: `click`, `pyyaml`, `pydantic`, `rich`, `cryptography`.

## About

Built by [Nomotic AI](https://nomotic.ai).

## License

Code: [MIT](LICENSE)
Specification (SPEC.md): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
