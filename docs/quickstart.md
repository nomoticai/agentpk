# Quickstart

Get up and running with agentpk in under five minutes.

## Prerequisites

- Python 3.10 or later
- pip

## Install

```bash
pip install agentpk
```

Verify the installation:

```bash
agent --version
```

## Create your first agent

Scaffold a new project:

```bash
agent init my-agent
```

This creates the following structure:

```
my-agent/
  manifest.yaml       # Agent metadata and configuration
  src/
    __init__.py
    agent.py           # Entry point
  requirements.txt     # Python dependencies
  README.md
  .gitignore
```

## Edit the manifest

Open `my-agent/manifest.yaml` and update the identity fields:

```yaml
spec_version: "1.0"
name: my-agent
version: "0.1.0"
description: "Summarises incoming support tickets."
author: "Your Name"
```

See [configuration.md](configuration.md) for the full manifest reference.

## Write your agent code

Edit `my-agent/src/agent.py`:

```python
def main() -> None:
    print("Hello from my-agent!")

if __name__ == "__main__":
    main()
```

The `main` function is declared in the manifest as the `entry_function`.
The runtime calls it when the agent starts.

## Validate

Check that the project is well-formed before packing:

```bash
agent validate my-agent/
```

Add `--verbose` for a per-stage breakdown:

```bash
agent validate my-agent/ --verbose
```

## Pack

Bundle the project into a portable `.agent` file:

```bash
agent pack my-agent/
```

This produces `my-agent-0.1.0.agent` in the parent directory of your
project. The `.agent` file is a ZIP archive containing your source code,
the manifest, and a `checksums.sha256` integrity file.

## Inspect

View the metadata embedded in a packed file:

```bash
agent inspect my-agent-0.1.0.agent
```

## Run

Execute the agent as a subprocess:

```bash
agent run my-agent-0.1.0.agent
```

> **Warning:** `agent run` executes code from the package. Only run agents
> from sources you trust.

Use `--dry-run` to validate without executing:

```bash
agent run my-agent-0.1.0.agent --dry-run
```

## Add code analysis

Run static analysis and embed a trust score in the package:

```bash
agent pack my-agent/ --analyze
```

The trust score tells consumers how well the manifest matches what the
code actually does. See [agent_analyzer.md](agent_analyzer.md) for the
full architecture.

## Sign and verify

Generate a key pair, sign the package, and verify it:

```bash
agent keygen --out my-key.pem
agent sign my-agent-0.1.0.agent --key my-key.pem
agent verify my-agent-0.1.0.agent --cert my-cert.pem
```

## Self-test

Run the built-in test suite to confirm agentpk is working correctly:

```bash
agent test
```

## Next steps

- [CLI Reference](cli.md) — every command and flag
- [Configuration Reference](configuration.md) — full manifest.yaml schema
- [Code Analysis](agent_analyzer.md) — trust scores and analysis levels
- [Specification](../SPEC.md) — the `.agent` format specification
