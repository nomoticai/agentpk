# Contributing to agentpk

## Setup

```bash
git clone https://github.com/nomoticai/agentpk.git
cd agentpk
pip install -e ".[dev]"
```

## Running tests

```bash
pytest tests/ -v
```

To measure coverage:

```bash
pytest --cov=agentpk tests/
```

## Running the CLI locally

After `pip install -e ".[dev]"`, the `agent` command is available in your shell:

```bash
agent init my-agent
agent pack my-agent/
agent validate my-agent-0.1.0.agent
agent inspect my-agent-0.1.0.agent
```

## Proposing spec changes

The `.agent` package format is defined in `SPEC.md`. If you want to propose a
change to the specification — new fields, new validation rules, new zones —
**open an issue first** describing the motivation and expected impact. Do not
open a pull request for spec changes without a prior discussion.

## Coding style

This project uses [Black](https://github.com/psf/black) for formatting and
[Ruff](https://github.com/astral-sh/ruff) for linting.

```bash
pip install black ruff
black src/ tests/
ruff check src/ tests/
```

Please run both before submitting a pull request.

## Pull requests

1. Fork the repo and create your branch from `main`.
2. Add tests for any new functionality.
3. Make sure the full test suite passes.
4. Open a pull request with a clear description of your changes.
