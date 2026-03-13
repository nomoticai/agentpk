# agentpk Examples

Example agent projects for learning the `.agent` package format and testing
your agentpk installation.

## Valid Examples

These agents are fully conformant and can be packed with `agent pack`.

| Directory | Language | Execution | Description |
|---|---|---|---|
| valid/fraud-detection | Python | scheduled | Financial fraud detection agent with tools |
| valid/customer-onboarding | Python | triggered | Event-driven customer onboarding workflow |
| valid/data-pipeline | Python | continuous | Long-running data ingestion pipeline |
| valid/invoice-processor | Python | on-demand | Full-schema example with every Zone 1 field |
| valid/node-agent | Node.js | on-demand | JavaScript web-scraper agent |

```bash
# Pack any valid example
agent pack examples/valid/fraud-detection

# Validate a packed file
agent validate fraud-detection-1.0.0.agent
```

## Invalid Examples

These agents are intentionally broken. Each demonstrates a specific
validation error that agentpk catches. See [invalid/README.md](invalid/README.md)
for the full table.

| Directory | Validation Stage | What fails |
|---|---|---|
| invalid/01-missing-manifest | Stage 1: Pre-flight | No manifest.yaml |
| invalid/02-malformed-yaml | Stage 1: Pre-flight | Broken YAML syntax |
| invalid/03-missing-spec-version | Stage 1: Pre-flight | Missing spec_version |
| invalid/04-invalid-name | Stage 2: Identity | Uppercase/spaces in name |
| invalid/05-missing-entry-point | Stage 3: File presence | Entry-point file missing |
| invalid/06-missing-deps | Stage 3: File presence | Dependencies file missing |
| invalid/07-invalid-exec-type | Stage 4: Consistency | Unrecognized execution type |
| invalid/08-scheduled-no-cron | Stage 4: Consistency | Scheduled with no cron |
| invalid/09-invalid-scope | Stage 4: Consistency | Invalid tool scope |
| invalid/10-invalid-language | Stage 4: Consistency | Unsupported language |
| invalid/11-env-overlap | Stage 4: Consistency | Env in allowed and denied |

```bash
# Each should fail -- that is correct behavior
agent pack examples/invalid/04-invalid-name
```

## Quick Test

Verify all valid examples pack and all invalid examples fail:

```bash
# Valid -- expect success
for dir in examples/valid/*/; do
  agent pack "$dir" && echo "OK: $dir" || echo "FAIL: $dir"
done

# Invalid -- expect failure
for dir in examples/invalid/*/; do
  agent pack "$dir" 2>&1 | head -1
done
```
