# Malformed YAML

manifest.yaml contains invalid YAML syntax (bad indentation).

Expected error (Stage 1 -- Pre-flight):
  ERROR: Failed to parse manifest.yaml: <YAML parse error details>

Run: `agent pack .`
