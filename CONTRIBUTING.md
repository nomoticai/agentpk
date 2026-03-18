# Contributing to agentpk

## Setup

```bash
git clone https://github.com/nomoticai/agentpk.git
cd agentpk
pip install -e ".[dev]"
```

For API development:

```bash
pip install -e ".[dev,api]"
```

## Running tests

```bash
pytest tests/ -v

# With coverage
pytest --cov=agentpk tests/

# API tests only (requires agentpk[api])
pytest tests/test_api.py -v

# SDK tests
pytest tests/test_sdk.py -v

# Extractor tests
pytest tests/test_extractors.py -v
```

## Running the CLI locally

After `pip install -e ".[dev]"`, the `agent` command is available:

```bash
agent init my-agent
agent pack my-agent/
agent validate my-agent-0.1.0.agent
agent inspect my-agent-0.1.0.agent
agent serve    # requires agentpk[api]
```

## Repository structure

```
src/agentpk/
    sdk.py              Public Python SDK — all CLI operations as typed functions
    cli.py              CLI — thin wrapper over SDK functions
    _internal/          Internal implementation modules (not public API)
    extractors/         Pluggable language-specific analysis extractors
        base.py         ExtractorBase ABC + StaticAnalysisFindings dataclass
        registry.py     ExtractorRegistry — maps language → extractor
        python_extractor.py
        nodejs_extractor.py
        typescript_extractor.py
        go_extractor.py
        java_extractor.py
        js_ast_helper.js    Bundled Node.js AST helper (acorn-based)
    api/                REST API (optional, pip install agentpk[api])
        app.py          FastAPI app factory
        routes.py       Route handlers
        models.py       Pydantic request/response models
        jobs.py         In-memory job store
        server.py       uvicorn entrypoint
        ui/             Packaging UI (single index.html)
```

## Adding a new language extractor

Adding support for a new language requires one new file:

1. Create `src/agentpk/extractors/<language>_extractor.py`
2. Implement `ExtractorBase` with `language`, `file_extensions`, and `extract()`
3. Register it in `src/agentpk/extractors/__init__.py`
4. Add test fixtures to `tests/fixtures/<language>-agent/`
5. Add tests to `tests/test_extractors.py`

The extractor must produce a `StaticAnalysisFindings` record. All
downstream logic (discrepancy classification, trust scoring, embedding)
is language-agnostic and requires no changes.

See `src/agentpk/extractors/go_extractor.py` for a simple pattern-based
example, or `src/agentpk/extractors/python_extractor.py` for a full
AST-based example.

## Proposing spec changes

The `.agent` package format is defined in `SPEC.md`. If you want to
propose a change to the specification — new fields, new validation
rules, new zones — **open an issue first** describing the motivation
and expected impact. Do not open a pull request for spec changes without
prior discussion.

## Coding style

This project uses [Black](https://github.com/psf/black) for formatting
and [Ruff](https://github.com/astral-sh/ruff) for linting.

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

SDK functions must never call `sys.exit()` or print to stdout — all
output through return values and typed exceptions.
