# Invalid Agent Examples

These directories contain intentionally broken agent projects. Each one
demonstrates a specific validation error that agentpk catches.

Use them to understand the validation rules, or to verify that your
installation is catching errors correctly.

| Directory | What it demonstrates |
|---|---|
| 01-missing-manifest | No manifest.yaml present |
| 02-malformed-yaml | manifest.yaml contains invalid YAML |
| 03-missing-spec-version | spec_version field is absent |
| 04-invalid-name | name contains uppercase letters and spaces |
| 05-missing-entry-point | declared entry_point file does not exist |
| 06-missing-deps | declared dependencies file does not exist |
| 07-invalid-exec-type | execution.type is not a recognized value |
| 08-scheduled-no-cron | type: scheduled but no schedule expression |
| 09-invalid-scope | a tool declares an unrecognized scope value |
| 10-invalid-language | runtime.language is not a supported language |
| 11-env-overlap | same environment in both allowed and denied lists |

## Usage

```bash
# Each of these should fail -- that is correct behavior
agent pack examples/invalid/04-invalid-name

# Run all invalid examples and confirm each fails
for dir in examples/invalid/*/; do
  echo "=== $dir ==="
  agent pack "$dir" --dry-run 2>&1 | head -3
  echo ""
done
```
