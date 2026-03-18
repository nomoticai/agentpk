# Changelog

All notable changes to agentpk will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.2] — 2026-03-18

### Added
- **Capabilities endpoint**: `GET /v1/capabilities` returns which analysis
  levels are available (LLM key detected, provider name, sandbox availability)
- **LLM key detection in UI**: Level 3 checkbox is automatically enabled or
  disabled based on whether `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set;
  shows provider name when available, info popup with setup instructions when not
- **Level 4 info tooltip**: inline help explaining sandbox requirements

### Changed
- **Signing migrated from RSA-2048 to Ed25519**
  - `agent keygen` now produces Ed25519 keypairs (.pem + .pub.pem)
  - `agent sign` now uses `--key` (private key) instead of `--key` + `--cert`
  - `agent verify` now uses `--key` (public key .pub.pem) instead of `--cert`
  - Signature files now include `"algorithm": "ed25519"` field
  - Private key size: ~119 bytes (was ~1,700 bytes for RSA-2048)
  - Signature size: 64 bytes (was 256 bytes for RSA-2048)
  - Packages signed with RSA must be re-signed — no backward compatibility
- **Packaging UI accepts folders directly**: users now select an agent folder
  instead of preparing an archive; client-side packaging is transparent
- **Level 4 label**: renamed from "Level 4 (Docker)" to "Level 4 (Sandbox)" —
  no mention of Docker in user-facing UI text
- **Button text**: initial state reads "Select an agent folder to begin";
  after folder selection reads "Package your agent"
- **Drop zone text**: reads "Drag your agent folder here"

### Notes
- SHA-256 package integrity hashes are unchanged
- Ed25519 is the current standard used by SSH, Signal, Let's Encrypt, and Git

---

## [0.2.1] — 2026-03-16

### Fix

- Skip API tests when fastapi is not installed

---

## [0.2.0] — 2026-03-16

### Added
- **Python SDK**: `from agentpk import pack, analyze, validate, inspect_package, init, diff, sign, verify`
  — all CLI operations now available as typed Python functions with dataclass return types
- Multi-language agent support: Node.js, TypeScript, Go, Java
- Pluggable extractor architecture (src/agentpk/extractors/) — new languages via single module addition
- Node.js AST-based signal extraction using acorn via bundled js_ast_helper.js
- TypeScript signal extraction extending Node.js extractor
- Go pattern-based signal extraction (imports, HTTP calls, subprocess, env vars)
- Java pattern-based signal extraction (imports, HTTP clients, subprocess, env vars, Spring AI @Tool)
- Language auto-detection from file extension distribution with developer warning
- `agent init --runtime` flag: nodejs, typescript, go, java
- Scaffold templates for Node.js, TypeScript, Go, Java projects
- 4 new self-test scenarios for multi-language validation
- Graceful Level 2 skip with documented reason for unsupported languages
- Typed exception hierarchy: AgentpkError, ManifestError, PackagingError, ValidationError, AnalysisError, PackageNotFoundError
- **REST API**: `pip install agentpk[api]` → `agent serve` → POST/GET /v1/packages
- **Packaging UI**: single-page web app served at / when API is running
- Async job model: submit → poll → download (handles long-running Level 3/4 analysis)
- API test suite in tests/test_api.py

### Changed
- CLI refactored to call SDK functions (zero behavior change for CLI users)
- analyzer.py refactored to use extractor registry (zero behavior change for Python agents)
- Internal modules moved to src/agentpk/_internal/ (not public API)
- constants.py: SUPPORTED_LANGUAGES and AST_LANGUAGES/PATTERN_LANGUAGES added
- manifest.py: language auto-detection helper added

### Notes
- Python analysis behavior is identical to v0.1.1; extractor refactor is internal only
- Node.js extractor requires Node.js on PATH for AST mode; falls back to pattern-based if unavailable
- Go and Java extractors are pattern-based and have no runtime dependencies
- SDK functions never call sys.exit() or print to stdout — all output through return values and exceptions

---

## [0.1.0] — 2026-03-12

Initial release of agentpk and the `.agent` open packaging standard.

### Added

**Format**
- `.agent` package format — portable archive with a structured manifest,
  source files, dependency declarations, and generated checksums
- `manifest.yaml` schema — full Zone 1 field specification covering
  identity, runtime, model preferences, framework, capabilities, 
  permissions, execution, and resources
- `checksums.sha256` — SHA-256 hash of every file in the package,
  generated automatically at pack time
- `_package` metadata block — tamper-evident record of format version,
  pack timestamp, packager identity, manifest hash, files hash, total
  file count, and package size
- Manifest hash binding — manifest is hashed before the `_package` block
  is written, ensuring the declared content is sealed into the package
- Support for Python, Node.js, TypeScript, Go, Java, and Ruby runtimes
- Support for on-demand, scheduled, triggered, and continuous execution types
- Tool capability declarations with scope (read, write, execute, delete,
  admin), required flag, targets, and constraints
- Data class permission declarations with access levels
- Environment allowlist and denylist
- Resource declarations (memory, CPU, network policy)
- Model preference declarations (preferred model, minimum context,
  alternatives, agnostic flag)
- Framework declarations (name and version constraint)
- Execution window constraints (permitted days, hours, timezone)
- Retry configuration (max attempts, backoff)

**Commands**
- `agent init <name>` — scaffold a new agent project with a manifest
  template, entry point, requirements file, and README
- `agent pack <dir>` — package an agent project into a `.agent` file.
  Flags: `--out-dir`, `--dry-run`
- `agent validate <target>` — validate an agent directory or packed
  `.agent` file through the 6-stage validation pipeline.
  Flags: `--verbose`
- `agent inspect <file>` — display manifest contents and package
  metadata in a formatted table
- `agent unpack <file> <dir>` — extract a `.agent` package to a directory
- `agent diff <file1> <file2>` — show manifest differences between two
  `.agent` packages
- `agent list <dir>` — list all `.agent` files in a directory with
  name, version, execution type, tool count, and pack date.
  Flags: `--recursive`, `--json`
- `agent run <file>` — execute a packed `.agent` file without manual
  extraction. Flags: `--dry-run`, `--keep`, `--env`
- `agent sign <file>` — cryptographically sign a `.agent` file with a
  private key
- `agent verify <file>` — verify the signature on a `.agent` file
- `agent keygen` — generate an Ed25519 key pair for signing
- `agent generate <dir>` — analyze source code and produce a
  `manifest.yaml`. Flags: `--level`, `--output`, `--force`
- `agent test` — run the agentpk self-test suite to verify installation.
  Flags: `--verbose`

**Validation pipeline**
- Stage 1 — Pre-flight: directory exists, manifest.yaml present,
  valid YAML, spec_version recognized
- Stage 2 — Identity: name regex, semver version, description,
  entry_point declared
- Stage 3 — File presence: entry_point file exists, dependencies
  file exists
- Stage 4 — Consistency: enum values, scheduled execution requires
  schedule expression, no environment overlap, valid tool scopes,
  valid runtime language
- Stage 5 — Checksums: file hashes match (packed files only)
- Stage 6 — Package integrity: manifest hash matches (packed files only)

**Trust score system**
- Level 1 — Structural validation (+20 points, -10 skip penalty)
- Level 2 — Static AST analysis (+30 points, -20 skip penalty)
  - Python: full AST walking via stdlib `ast` module
  - Node.js/TypeScript: regex-based pattern analysis
  - Detects imports, network calls, file I/O, subprocess calls,
    env var access, tool framework registrations, entry functions
  - Framework detection: LangChain, OpenAI functions, CrewAI, AutoGen
- Level 3 — LLM semantic analysis (+25 points, -15 skip penalty)
  - Provider auto-detection: Anthropic (claude-haiku) or OpenAI (gpt-4o-mini)
  - Citation-required prompting — LLM must cite file:line for every claim
  - Cross-referenced against static analysis findings
  - No LLM SDK dependency — calls via `urllib.request`
- Level 4 — Runtime sandbox (+25 points, -25 skip penalty)
  - Docker-based isolated execution
  - Network interception and behavioral observation
  - Comparison of observed behavior against manifest declarations
- Discrepancy types: undeclared, unconfirmed, scope_mismatch
- Discrepancy severities: minor (-5), major (-10), critical (-20)
- Trust labels: Verified (90-100), High (75-89), Moderate (60-74),
  Low (40-59), Unverified (0-39)
- Analysis block embedded in `_package` metadata when `--analyze` is used
- Graceful degradation when LLM or Docker unavailable — skips level,
  subtracts penalty, packs successfully
- `--strict` flag — fails pack if requested analysis level cannot be reached
- `--on-discrepancy` flag — warn (default), fail, or auto

**Examples**
- `examples/valid/fraud-detection` — triggered execution, multi-tool,
  real-time monitoring pattern
- `examples/valid/customer-onboarding` — on-demand execution,
  LLM integration pattern
- `examples/valid/data-pipeline` — scheduled execution, data
  processing pattern
- `examples/valid/invoice-processor` — full schema, every Zone 1 field
- `examples/valid/node-agent` — Node.js runtime, language-agnostic
  packaging demonstration
- `examples/invalid/` — 11 intentionally broken agents demonstrating
  each validation error with expected error messages

**JSON Schema**
- `schema/manifest.schema.json` — JSON Schema for manifest.yaml
  compatible with VS Code autocomplete via SchemaStore

**Documentation**
- `README.md` — installation, quickstart, command reference
- `SPEC.md` — `.agent` format specification (CC BY 4.0)
- `WHY.md` — problem statement and use case narratives
- `TRUST.md` — trust score reference guide and recommended minimums
- `SECURITY.md` — security model, limitations, and responsible disclosure
- `CONTRIBUTING.md` — contributor guide
- `examples/README.md` — example index with usage instructions
- Per-example READMEs with validation and pack commands

**Testing**
- 87 unit tests across validator, manifest, packer, checksums, and
  self-test modules
- `agent test` self-test suite — 14 integration test cases covering
  valid and invalid agents, generated at runtime into a temp directory
- Integration test coverage: all 6 validation stages, pack/unpack round
  trip, diff, init scaffold, JSON schema validity

**CI/CD**
- `.github/workflows/ci.yml` — runs test suite on Python 3.10, 3.11,
  3.12 across Ubuntu, macOS, Windows
- `.github/workflows/publish.yml` — publishes to PyPI on version tag

### Notes

The `.agent` format specification is published under CC BY 4.0. The
agentpk CLI is published under the MIT License. Both are maintained
by Nomotic AI.

The `.nomo` sealed package format — Nomotic's governed packaging format
for runtime-governed agent deployment — is a separate specification
built on top of `.agent`. It is maintained in a separate repository.

---

[Unreleased]: https://github.com/nomoticai/agentpk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nomoticai/agentpk/releases/tag/v0.1.0
