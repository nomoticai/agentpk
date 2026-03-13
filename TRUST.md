# Trust Scores

Every `.agent` package that is built with code analysis enabled carries
a trust score — a number from 0 to 100 that represents how well the
manifest has been verified against what the code actually does.

This document explains what the score means, how it is calculated,
how to interpret it, and what minimum scores to require in different
contexts.

---

## What a trust score measures

The trust score measures **agreement between the manifest and the code**.

A high score means: multiple independent analysis methods examined this
code and confirmed that the manifest accurately describes what the agent
does, what it accesses, and what it can affect.

A low score means one of two things: the manifest was not verified
against the code, or verification found things the manifest did not
declare.

The score does not measure code quality, security posture, or whether
the agent is a good idea. It measures one specific thing: does the
manifest tell an accurate story about this code?

---

## Analysis levels

Trust scores are built from up to four independent evidence sources.
Each runs if the required tooling is available. Each contributes to or
reduces the final score.

### Level 1 — Structural validation (max +20 points)

Validates the manifest schema, required fields, and enum values using
the agentpk validation pipeline. A manifest that fails structural
validation cannot produce a valid package.

Requires nothing. Runs on any machine.

Skip penalty: -10 (no manifest present).

### Level 2 — Static AST analysis (max +30 points)

Walks every source file using Python's `ast` module (for Python agents)
or regex-based analysis (for Node.js and TypeScript). Extracts:

- All imports and external dependencies
- Network calls (requests, httpx, aiohttp, LLM client libraries)
- File system operations (reads and writes, with scope detection)
- Subprocess calls
- Environment variable access
- Tool framework registrations (LangChain, OpenAI functions, CrewAI, AutoGen)
- Entry functions

Compares findings against the manifest. Flags anything found in code
that is not declared, and anything declared that is not found in code.

Requires nothing. Runs on any machine. Results are deterministic.

Skip penalty: -20.

### Level 3 — LLM semantic analysis (max +25 points)

Sends source files to a language model and asks it to generate what the
manifest should say based purely on the code, with citations to specific
file and line numbers for every claim.

Compares LLM findings against the manifest and against Level 2 results.
Findings confirmed by both static analysis and LLM carry higher
confidence. LLM findings without code citations are weighted at 50%.

Requires `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in the environment.
Uses `claude-haiku-4-5-20251001` or `gpt-4o-mini` for cost efficiency.

Skip penalty: -15.

### Level 4 — Runtime sandbox (max +25 points)

Executes the agent in an isolated Docker container with network
interception enabled. Observes actual system behavior: what network
calls were made, what files were written, what environment variables
were read, what external systems were contacted.

Compares observed behavior against manifest declarations. The sandbox
catches dynamic behavior that static analysis cannot — behavior that
only appears at runtime, conditional on execution paths.

Requires Docker installed and running.

Skip penalty: -25.

---

## Score calculation

```
base = 0

if level 1 ran:  base += level_1_score   (0 to 20)
if level 2 ran:  base += level_2_score   (0 to 30)
if level 3 ran:  base += level_3_score   (0 to 25)
if level 4 ran:  base += level_4_score   (0 to 25)

if level 1 skipped:  base -= 10
if level 2 skipped:  base -= 20
if level 3 skipped:  base -= 15
if level 4 skipped:  base -= 25

trust_score = max(0, base)
```

Discrepancies reduce the score of the level that found them:

| Severity | Penalty | Triggered by |
|---|---|---|
| Minor | -5 per item | Declared tool not found in code |
| Major | -10 per item | Code uses network but no tool declared |
| Critical | -20 per item | Declared read scope but code does write |

The floor is 0. Scores do not go negative.

---

## Score interpretation

| Score | Label | What it means |
|---|---|---|
| 90–100 | Verified | All available levels passed. No discrepancies. The manifest is well-supported by the code. |
| 75–89 | High | Most levels passed. Minor gaps or one skipped level. The manifest is likely accurate. |
| 60–74 | Moderate | Partial analysis, some discrepancies, or multiple skipped levels. Warrants closer review. |
| 40–59 | Low | Limited analysis or significant discrepancies. Treat the manifest as unverified. |
| 0–39 | Unverified | Minimal analysis was performed. The manifest is a declaration only, not a verification. |

---

## What each discrepancy type means

**Undeclared capability** — the analysis found something in the code that
is not declared in the manifest. The agent may be able to do something
the manifest does not mention. This is the most important discrepancy
type for security review.

Examples:
- `psycopg2` imported but no database `data_class` declared
- `requests.post` found but no write-scope tool declared
- `subprocess.run` found but no execute-scope tool declared

**Unconfirmed declaration** — the manifest declares a capability but
analysis could not confirm it exists in the code. This may mean the
capability is unused, conditionally activated, or the manifest was
written speculatively.

Examples:
- Manifest declares a `notify_team` tool but no corresponding code found
- Manifest declares file write permissions but no file write calls detected

**Scope mismatch** — the manifest declares one level of access but the
code demonstrates a higher level. The most serious discrepancy type.

Examples:
- Tool declared as `scope: read` but code calls `requests.post`
- Tool declared as `scope: read` but code calls `cursor.execute(INSERT ...)`

---

## Reading the analysis block

Every package built with `--analyze` includes an analysis block in its
package metadata. Run `agent inspect` to see it:

```
               Trust Score
┌──────────────────────┬────────────────────────────────────┐
│ score                │ 82/100  (High)                     │
│ levels run           │ 1, 2, 3                            │
│ levels skipped       │ 4  (-25 pts, Docker not available) │
│ discrepancies        │ none                               │
│ analyzed at          │ 2026-03-12T23:44:45Z               │
│ llm provider         │ anthropic/claude-haiku-...         │
└──────────────────────┴────────────────────────────────────┘
```

A package without an analysis block shows:

```
               Trust Score
┌──────────────────────┬────────────────────────────────────┐
│ score                │ unverified (no analysis performed) │
└──────────────────────┴────────────────────────────────────┘
```

No analysis block means the package was built without `--analyze`. The
manifest is a declaration only.

---

## Recommended minimums by context

These are starting points, not mandates. Every organization should set
its own thresholds based on risk tolerance and agent capability.

### Internal development

**Minimum: none required**

Teams building and iterating on agents internally can use whatever
analysis level fits their workflow. Trust scores become more valuable
as agents move toward production or cross team boundaries.

### Staging and pre-production

**Minimum: 60 (Moderate)**

Requires at least Level 1 and Level 2 to have run and passed. Static
analysis should confirm the manifest is not materially inaccurate before
an agent runs in a pre-production environment.

```bash
agent pack . --analyze --level 2
```

### Production deployment

**Minimum: 75 (High)**

Requires Level 1, Level 2, and either Level 3 or Level 4 to have run.
Both static analysis and a second verification method should confirm
the manifest before an agent runs in production.

```bash
agent pack . --analyze --level 3
# or
agent pack . --analyze --level 4
```

### Third-party and vendor agents

**Minimum: 80**

Agents arriving from outside your organization should have passed at
least three analysis levels with no discrepancies. A score below 80
should prompt a conversation with the vendor about what analysis was
performed.

### Security-sensitive environments

**Minimum: 90 (Verified)**

Requires all available levels to have passed with no discrepancies.
Use `--strict` to enforce this at build time:

```bash
agent pack . --analyze --level 4 --strict
```

`--strict` causes the pack to fail if the requested level cannot be
reached. A package that cannot be produced with a 90+ score should not
be deployed in a security-sensitive environment without explicit review
and exception approval.

---

## What a trust score does not guarantee

**It does not guarantee the agent is safe to run.** A score of 100 means
the manifest accurately describes the code. It does not mean the code
does something appropriate, well-designed, or free of vulnerabilities.

**It does not guarantee complete coverage.** Static analysis can miss
dynamically constructed code. LLM analysis can miss things static
analysis catches. Sandbox execution is best-effort and may not trigger
all code paths. No analysis system provides complete coverage.

**It does not prevent a determined bad actor.** Someone who understands
how the analysis works can potentially construct code that passes
analysis while concealing capabilities. The trust score is a
verification tool for honest manifests, not a security control against
adversarial ones.

**It does not replace security review.** For high-stakes agents in
sensitive environments, human security review of the source code remains
appropriate. The trust score reduces the burden of that review — it
tells reviewers where to focus and what the automated analysis already
confirmed. It does not replace it.

---

## Generating a trust score

Add `--analyze` to any `agent pack` command:

```bash
# Level 2 only — no external dependencies
agent pack . --analyze --level 2

# Level 3 — requires API key
agent pack . --analyze --level 3

# Highest available — auto-detects environment
agent pack . --analyze

# Strict — fails if level 3 cannot be reached
agent pack . --analyze --level 3 --strict
```

To generate a manifest from code before packing:

```bash
agent generate .          # analyzes code and produces manifest.yaml
agent pack . --analyze    # verifies manifest against code and packs
```
