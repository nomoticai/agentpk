# Missing spec_version

manifest.yaml is valid YAML but missing the required spec_version field.

Expected error (Stage 1 -- Pre-flight):
  ERROR: spec_version is required

Run: `agent pack .`
