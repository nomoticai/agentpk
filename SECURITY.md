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

This means a valid package is guaranteed to be exactly what was produced
at pack time. You can verify at any time that a package you received
is identical to the package that was built.

### Version binding

The manifest `name` and `version` fields are included in the manifest
hash. A package cannot have its version number changed without
invalidating the hash. The version you see in `agent inspect` is the
version that was sealed into the package.

### No external dependencies for verification

Tamper detection requires nothing beyond `agentpk` itself. No API keys,
no network access, no external services. Verification works offline.

---

## What the format does not guarantee

### Manifest accuracy

**The manifest is a declaration. agentpk cannot prove it is truthful.**

A developer can write `scope: read` in a manifest and include write
operations in the code. A developer can omit capabilities that exist in
the code. The manifest is authored by a human, and humans can be wrong
or dishonest.

The trust score system (see [TRUST.md](TRUST.md)) provides machine-
computed evidence about manifest accuracy. Static analysis, LLM review,
and runtime sandbox observations all contribute to the score. But no
automated analysis provides certainty. A score of 100 means strong
evidence of agreement between manifest and code. It does not mean proof.

For agents in security-sensitive contexts, human review of source code
remains appropriate. The trust score reduces the burden of that review —
it directs attention to areas of uncertainty — it does not replace it.

### Runtime behavior

agentpk governs the packaging and delivery of agents. It does not govern
what an agent does when it executes in production.

A packaged agent with an accurate, fully-verified manifest can still:
- Behave differently in production than it did during analysis
- Drift over time as model behavior changes
- Take actions that are within its declared scope but outside intent
- Interact with other agents in ways that produce unintended outcomes

Runtime behavioral governance — enforcing that agents only do what they
declared during execution, detecting drift, and interrupting unauthorized
actions — is a separate problem addressed by runtime governance tooling.
agentpk handles the packaging layer.

### Identity of the packager

The tamper-evident hash chain proves a package was not modified after
it was built. It does not prove who built it.

If you receive a `.agent` file and want to verify it came from a specific
individual or organization, you need a cryptographic signature in
addition to the package hash. See `agent sign` and `agent verify` in the
command reference.

---

## The false manifest problem

This deserves direct treatment because it is the most important security
limitation of the format.

Scenario: a vendor delivers `data-processor-1.0.0.agent`. The manifest
declares three read-scope tools and no write operations. The trust score
is 45 — human-declared, no analysis performed. Inside the package, the
code contains a `requests.post()` call to an external API that the
manifest does not mention.

agentpk will:
- Successfully validate the package (hashes are intact)
- Show a trust score of 45 with "no analysis performed"
- Display the declared manifest accurately

agentpk will not:
- Detect the undeclared network call (no analysis was run)
- Prevent the package from being used

The trust score of 45 is a signal that this package has not been
verified. A policy of requiring a minimum trust score of 75 before
accepting third-party packages would surface this gap and prompt the
receiver to request a package built with analysis enabled.

With analysis enabled, the undeclared `requests.post()` would be
detected as a MAJOR discrepancy by Level 2 static analysis. The trust
score would drop significantly. The receiver would see the discrepancy
in `agent inspect` and know to investigate before deploying.

The format is designed so that lazy or careless manifests are visible,
and thorough analysis is rewarded with a higher score. It is not designed
to catch a sophisticated bad actor who understands the analysis system
and deliberately evades it.

For agents from untrusted sources in high-stakes environments, treat
the trust score as a filter that reduces the cost of human review, not
as a substitute for it.

---

## Responsible disclosure

If you discover a security vulnerability in agentpk itself — the CLI,
the packaging format, the analysis system, or the validation pipeline —
please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Email: security@nomotic.ai

Include:
- A description of the vulnerability
- Steps to reproduce
- The agentpk version affected
- Your assessment of severity and impact

We will acknowledge receipt within 48 hours and aim to produce a fix
within 14 days for critical issues. We will credit you in the release
notes unless you prefer to remain anonymous.

---

## Known limitations

These are documented limitations, not vulnerabilities:

**Dynamic code generation.** Static AST analysis cannot detect
capabilities that are generated at runtime from strings, loaded from
external sources, or constructed dynamically. An agent that builds a
network request URL at runtime from concatenated strings may not trigger
static analysis detection. Sandbox execution (Level 4) reduces this gap
but does not eliminate it.

**Obfuscated code.** Code that is deliberately obfuscated to evade
analysis will reduce trust score accuracy. The analysis system is not
designed to defeat adversarial obfuscation.

**Multi-file dynamic imports.** Python's `importlib` and `__import__`
dynamic import mechanisms may not be detected by AST analysis in all
cases. Known patterns are detected. Unknown dynamic import patterns may
be missed.

**Node.js analysis is regex-based.** JavaScript and TypeScript files are
analyzed using pattern matching, not a full AST parser. Complex code
patterns may not be detected.

**Sandbox coverage is not complete.** The Level 4 sandbox runs the agent
for a limited time with a test invocation. Code paths that only execute
under specific conditions, with specific inputs, or after extended
operation may not be triggered during sandbox analysis.

---

## Dependency security

agentpk's core dependencies:

| Package | Purpose | Notes |
|---|---|---|
| `click` | CLI framework | Well-maintained, widely used |
| `pyyaml` | YAML parsing | Use `yaml.safe_load` only — enforced |
| `pydantic` | Data validation | v2, type-safe |
| `rich` | Terminal output | No network access |
| `cryptography` | Signing operations | OpenSSL bindings |

agentpk does not make network calls during normal operation. `agent
analyze --level 3` calls an LLM API using `urllib.request` from the
Python stdlib. No third-party HTTP library is used for this.

The `openai` and `anthropic` Python SDKs are not dependencies. LLM API
calls are made directly to avoid transitive dependency exposure.

---

## Version support

Security fixes are applied to the current release only. We do not
backport security fixes to older versions. Keep agentpk up to date:

```bash
pip install --upgrade agentpk
```

Check your current version:

```bash
agent --version
```
