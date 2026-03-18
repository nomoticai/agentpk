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

### Level 2 — Static code analysis (max +30 points)

Analyzes every source file using language-specific extractors. The
extractor architecture is pluggable — each language has its own
extraction module producing a standard `StaticAnalysisFindings` record.
All downstream discrepancy classification and scoring is language-agnostic.

**Python** — full AST traversal using the stdlib `ast` module.
Deterministic and deep. Detects imports, HTTP method classifications,
tool framework registrations (LangChain, OpenAI functions, CrewAI,
AutoGen), dynamic imports, and obfuscated calls.

**Node.js** — AST-based using acorn via a bundled helper script.
Falls back to pattern-based if Node.js is not on PATH; the analysis
record documents which mode ran. Detects require/import statements,
axios/fetch/http method calls, fs operations, child_process calls,
process.env access, and LangChain.js tool registrations.

**TypeScript** — extends the Node.js extractor using
@typescript-eslint/parser. Falls back to the Node.js extractor if
the TypeScript parser is unavailable.

**Go** — pattern-based on source text, no subprocess required. Detects
import blocks, net/http calls with method classification, os/ioutil file
operations, exec.Command, and os.Getenv/LookupEnv.

**Java** — pattern-based on source text. Detects import statements,
HttpClient/OkHttpClient/RestTemplate usage, FileWriter/Files.write
operations, Runtime.exec/ProcessBuilder, System.getenv, and Spring AI
@Tool annotations.

**Unsupported languages** — Level 2 is skipped with the reason
`"no extractor available for language: <lang>"` recorded in the analysis
block. The -20 skip penalty applies.

Signals extracted across all languages:

- All imports and external dependencies
- Network calls with HTTP method classification (GET, POST, PUT, DELETE, etc.)
- File system operations (reads and writes, with scope detection)
- Subprocess calls
- Environment variable access
- Tool framework registrations (framework name, tool name, file, line)
- Entry functions

Results are compared against the manifest. Findings in code not declared
in the manifest, and declarations not found in code, both produce
discrepancy records.

Requires nothing beyond the agentpk install. Results are deterministic.

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

If the sandbox reaches the time limit before completing, a timeout
advisory signal is recorded and Level 4's contribution is multiplied
by 0.8. Partial observation is retained and scored; it is not discarded.

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

LLM-only findings (not confirmed by Level 2 static analysis) apply a
0.5x weight modifier to their penalty. A major LLM-only finding
contributes -5 effective penalty rather than -10.

Sandbox timeout applies a 0.8x confidence modifier to Level 4's weight
contribution. Partial observation is better than none.

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
- `axios.post` in Node.js code but no write-scope tool declared
- `exec.Command` in Go code but no subprocess capability declared

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
- Tool declared as `scope: read` but Node.js code calls `fs.writeFile`

---

## Deduplication

A capability detected as undeclared by both Level 2 and Level 3 produces
one discrepancy record with `source: static+llm` and the full severity
penalty applied once, not twice.

A capability confirmed by Level 2, Level 3, and Level 4 produces one
record with `source: triple-confirmed` — the highest evidential
confidence classification.

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

No analysis block means the package was built without `--analyze`. This
is a distinct state from a score of zero — zero means analysis ran and
found significant problems; unverified means analysis was not performed.

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

Requires at least Level 1 and Level 2 to have run and passed.

```bash
agent pack . --analyze --level 2
```

### Production deployment

**Minimum: 75 (High)**

Requires Level 1, Level 2, and either Level 3 or Level 4.

```bash
agent pack . --analyze --level 3
```

### Third-party and vendor agents

**Minimum: 80**

Agents from outside your organization should have passed at least three
analysis levels with no discrepancies.

### Security-sensitive environments

**Minimum: 90 (Verified)**

```bash
agent pack . --analyze --level 4 --strict
```

`--strict` causes the pack to fail if the requested level cannot be
reached.

---

## What a trust score does not guarantee

**It does not guarantee the agent is safe to run.** A score of 100 means
the manifest accurately describes the code. It does not mean the code
is appropriate, well-designed, or free of vulnerabilities.

**It does not guarantee complete coverage.** No analysis system provides
complete coverage. Static analysis misses dynamically constructed code.
LLM analysis misses things static analysis catches. Sandbox execution
may not trigger all code paths.

**It does not prevent a determined bad actor.** The trust score is a
verification tool for honest manifests, not a security control against
adversarial ones.

**It does not replace security review.** For high-stakes agents in
sensitive environments, human review of source code remains appropriate.
The trust score reduces the burden of that review — it does not
replace it.

---

## Generating a trust score

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

Via the Python SDK:

```python
from agentpk import analyze, pack

result = analyze("./my-agent", levels=[1, 2, 3])
print(result.trust_score, result.trust_label)

result = pack("./my-agent", analyze=True)
print(result.trust_score, result.package_path)
```
