# Security

This document describes what the `.agent` format and agentpk tooling
provide as security properties, what they explicitly do not provide,
and how to report vulnerabilities in agentpk itself.

---

## What the format guarantees

### Tamper detection

Every `.agent` package contains:

- A SHA-256 hash of every file in the package
- A SHA-256 hash of the manifest
- A SHA-256 hash of the complete file collection

These are computed at pack time and embedded in the package. They cannot
be changed without repacking the package from source.

When you run `agent validate package.agent`, agentpk recomputes all
hashes and compares them against the stored values. If any file has been
modified — any byte in any file — validation fails.

### Version binding

The manifest `name` and `version` fields are included in the manifest
hash. A package cannot have its version number changed without
invalidating the hash.

### No external dependencies for verification

Tamper detection requires nothing beyond `agentpk` itself. No API keys,
no network access, no external services. Verification works offline.

---

## What the format does not guarantee

### Manifest accuracy

**The manifest is a declaration. agentpk cannot prove it is truthful.**

A developer can write `scope: read` in a manifest and include write
operations in the code. The trust score system (see [TRUST.md](TRUST.md))
provides machine-computed evidence about manifest accuracy. But no
automated analysis provides certainty. A score of 100 means strong
evidence of agreement between manifest and code. It does not mean proof.

### Runtime behavior

agentpk governs the packaging and delivery of agents. It does not govern
what an agent does when it executes in production. Runtime behavioral
governance is a separate problem addressed by runtime governance tooling.

### Identity of the packager

The tamper-evident hash chain proves a package was not modified after
it was built. It does not prove who built it. For identity verification,
use `agent sign` and `agent verify`.

---

## The false manifest problem

This deserves direct treatment because it is the most important security
limitation of the format.

Scenario: a vendor delivers `data-processor-1.0.0.agent`. The manifest
declares three read-scope tools and no write operations. The trust score
is 45 — human-declared, no analysis performed. Inside the package, the
code contains a `requests.post()` call to an external API that the
manifest does not mention.

agentpk will validate the package (hashes are intact) and display the
declared manifest accurately. It will not detect the undeclared network
call if no analysis was run.

With analysis enabled, the undeclared `requests.post()` would be
detected as a major discrepancy by Level 2 static analysis for all
supported languages (Python, Node.js, TypeScript, Go, Java). The trust
score would drop significantly and the discrepancy would appear in
`agent inspect`.

A policy of requiring a minimum trust score before accepting third-party
packages is the recommended mitigation.

---

## Responsible disclosure

If you discover a security vulnerability in agentpk — the CLI,
the packaging format, the analysis system, the REST API, or the
validation pipeline — please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Email: security@nomotic.ai

Include a description of the vulnerability, steps to reproduce, the
agentpk version affected, and your assessment of severity. We will
acknowledge within 48 hours and aim to fix critical issues within 14
days.

---

## Known limitations

**Dynamic code generation.** Static analysis cannot detect capabilities
constructed at runtime from strings or loaded dynamically. Sandbox
execution (Level 4) reduces this gap. Known dynamic import patterns
(importlib, __import__, computed require()) are detected and flagged as
advisory signals passed to Level 3 for LLM evaluation.

**Pattern-based analysis for Go and Java.** These languages are analyzed
using regex patterns on source text, not a full AST parser. Complex
patterns — method chaining, aliased imports, reflection — may not be
detected. The analysis record documents the extractor used.

**Node.js fallback mode.** If Node.js is not available on PATH, the
Node.js extractor falls back to pattern-based analysis. The analysis
record documents which mode ran.

**Sandbox coverage is not complete.** The Level 4 sandbox runs for a
limited time with a test invocation. Code paths triggered only under
specific conditions may not execute. A timeout advisory signal is
recorded when the sandbox reaches its time limit; Level 4's contribution
is reduced by a 0.8 confidence modifier rather than discarded entirely.

**REST API authentication.** The API server started with `agent serve`
does not require authentication by default. When exposing the API on a
network, restrict access at the network or reverse proxy layer.
Authentication will be added in a future release.

**Obfuscated code.** The analysis system flags known obfuscation
patterns as advisory signals. It is not designed to defeat adversarial
obfuscation comprehensively.

---

## Dependency security

Core dependencies:

| Package | Purpose |
|---------|---------|
| `click` | CLI framework |
| `pyyaml` | YAML parsing — `yaml.safe_load` only, enforced |
| `pydantic` | Data validation (v2) |
| `rich` | Terminal output — no network access |
| `cryptography` | Signing operations (OpenSSL bindings) |

API extras (`pip install agentpk[api]`):

| Package | Purpose |
|---------|---------|
| `fastapi` | REST API framework |
| `uvicorn` | ASGI server |
| `python-multipart` | File upload parsing |

agentpk does not make network calls during normal operation. LLM API
calls (Level 3 analysis) use `urllib.request` from the Python stdlib.
The `openai` and `anthropic` SDKs are not dependencies.

---

## Version support

Security fixes apply to the current release only.

```bash
pip install --upgrade agentpk
agent --version
```
