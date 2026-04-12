# Agent Intelligence Record (AIR) Specification

**Version:** 1.0
**Status:** Draft
**Spec URL:** https://agentpk.io/specs/air/v1.0
**License:** CC BY 4.0

---

## Overview

The Agent Intelligence Record (AIR) is an open, schema-defined standard for
portable agent memory. An AIR bundle captures the operational intelligence an
agent has accumulated — its behavioral history, statistical profile, trust
trajectory, organizational knowledge, and distilled insights — in a format any
platform can consume without requiring the issuing platform.

AIR is to agent memory what OpenAPI is to APIs: a versioned, platform-agnostic
contract that travels with the artifact.

An AIR bundle is embedded inside a `.agent` package under the `intelligence/`
directory, or referenced via the `_package.air` manifest block for inline
snapshots.

---

## Bundle Structure

```
my-agent.agent/
└── intelligence/
    ├── air.json            ← manifest (required)
    ├── audit.jsonl         ← transaction history (optional)
    ├── fingerprint.json    ← behavioral profile (optional)
    ├── trust.json          ← trust trajectory (optional)
    ├── org_context.json    ← organizational knowledge (optional)
    └── knowledge_state.json ← distilled insights (optional)
```

The `air.json` manifest is the only required file. All component files are
optional. A bundle with only `air.json` is valid; it declares the agent's
identity and export provenance with no behavioral data.

---

## Components

### `air.json` — Bundle Manifest (required)

```json
{
  "air_version": "1.0",
  "spec": "https://agentpk.io/specs/air/v1.0",
  "agent_id": "string",
  "certificate_id": "string | null",
  "issuing_platform": "string",
  "issuing_platform_version": "string",
  "export_timestamp": "ISO 8601",
  "components": ["audit", "fingerprint", "trust", "org_context", "knowledge_state"],
  "component_hashes": {
    "audit": "sha256:...",
    "fingerprint": "sha256:...",
    "trust": "sha256:...",
    "org_context": "sha256:...",
    "knowledge_state": "sha256:..."
  },
  "export_sig": "ed25519:...",
  "redaction_profile": "minimal | standard | strict",
  "intelligence_license": {
    "default": "proprietary",
    "components": {
      "fingerprint": "cc-by-nc-4.0",
      "audit": "proprietary"
    },
    "permitted_uses": ["rehydration", "governance"],
    "prohibited_uses": ["fine-tuning", "benchmarking", "re-export"]
  }
}
```

`component_hashes` lists only components present in the bundle. Components
listed in `components` but absent from the archive are a conformance error.

`intelligence_license.default` applies to all components not listed under
`intelligence_license.components`. Per-component values override the default.

`export_sig` is an Ed25519 signature over the canonical JSON serialization of
`air.json` with `export_sig` set to `null`. Optional but recommended.

---

### `audit.jsonl` — Transaction History

Hash-chained audit records in newline-delimited JSON. Each line is one record.

```json
{"seq": 1, "ts": "ISO 8601", "action": "string", "verdict": "ALLOW|DENY|ESCALATE", "hash": "sha256:...", "prev_hash": "sha256:..."}
```

The first record has `"prev_hash": "genesis"`. Each record's `hash` is
SHA-256 of the canonical JSON of the record with `hash` set to `null`.

**Manifest fields:**

```json
{
  "air_version": "1.0",
  "record_count": 4721,
  "audit_format": "jsonl | jsonl.gz | zstd | parquet",
  "chain_head": "sha256:...",
  "chain_tail": "sha256:...",
  "export_sig": "ed25519:...",
  "redaction_profile": "minimal | standard | strict",
  "date_range": {
    "from": "ISO 8601",
    "to": "ISO 8601"
  }
}
```

The `chain_tail` hash MUST be present in every export regardless of
`audit_format` or whether `summary_only` mode is used. This allows a
consuming platform to verify the summary was derived from a complete,
unbroken chain.

**Redaction profiles:**
- `minimal` — removes free-text fields only
- `standard` — removes PII identifiers, keeps statistical shape
- `strict` — retains only verdict, timestamp, and hash per record

---

### `fingerprint.json` — Behavioral Profile

Statistical description of the agent's action patterns.

```json
{
  "air_version": "1.0",
  "agent_id": "string",
  "total_observations": 4721,
  "confidence": 0.94,
  "action_distribution": {"read": 0.71, "write": 0.22, "query": 0.07},
  "target_distribution": {"customer_records": 0.43, "product_catalog": 0.31},
  "temporal_profile": {
    "peak_hours": [9, 10, 14, 15],
    "burst_threshold": 12.4
  },
  "outcome_distribution": {"ALLOW": 0.89, "DENY": 0.06, "ESCALATE": 0.05},
  "drift_baseline_jsd": 0.08
}
```

---

### `trust.json` — Trust Trajectory

Time-series of trust score changes with labeled events.

```json
{
  "air_version": "1.0",
  "current_score": 0.87,
  "trajectory": [
    {"ts": "ISO 8601", "score": 0.72, "event": "initial"},
    {"ts": "ISO 8601", "score": 0.61, "event": "drift_detected"},
    {"ts": "ISO 8601", "score": 0.78, "event": "drift_resolved"},
    {"ts": "ISO 8601", "score": 0.87, "event": "elevated_trust"}
  ],
  "trajectory_label": "recovered_stable | rising | declining | stable | volatile"
}
```

---

### `org_context.json` — Organizational Knowledge

Institutional context that makes the agent specific to an organization.

```json
{
  "air_version": "1.0",
  "org_id": "string",
  "values": ["accuracy over speed", "always escalate on ambiguity in financial context"],
  "vocabulary": {
    "preferred": {"client": "member", "fee": "investment"},
    "prohibited": ["guaranteed", "risk-free"]
  },
  "domain_anchors": ["healthcare compliance", "HIPAA", "prior authorization"],
  "escalation_patterns": []
}
```

---

### `knowledge_state.json` — Distilled Insights (optional)

Structured summary of what the agent has come to know, distilled from
operational history. This is derived intelligence, not raw history.

```json
{
  "air_version": "1.0",
  "snapshot_timestamp": "ISO 8601",
  "distillation_method": "nomotic-v1 | manual | external",
  "summary_count": 142,
  "key_insights": [
    {
      "id": "ki-001",
      "domain": "escalation_patterns",
      "content": "string",
      "confidence": 0.91,
      "source_record_count": 312,
      "created": "ISO 8601"
    }
  ],
  "embeddings": {
    "provider": "openai",
    "model": "text-embedding-3-small",
    "dimension": 1536,
    "version": "1",
    "entry_count": 142,
    "storage": "inline | cid"
  },
  "cid_root": "ipfs://... | null"
}
```

`embeddings` is optional. `cid_root` is optional. `key_insights` may be
an empty array. `distillation_method` is required — consuming platforms
use it to calibrate how much to trust the insights.

---

## Conformant Consumer Requirements

A platform that imports an AIR bundle MUST:

1. **Verify all hashes before import.** Recompute SHA-256 for each component
   file and compare against `component_hashes` in `air.json`. Reject the
   bundle if any hash does not match.

2. **Verify the export signature if present.** If `export_sig` is set in
   `air.json`, verify it before importing. A failed signature MUST cause
   rejection unless the operator explicitly overrides with `--trust-unsigned`.

3. **Apply the redaction profile.** Never re-introduce data that the
   redaction profile removed. The `redaction_profile` field is informational
   for the consumer; stripping must have occurred at export time.

4. **Honor the `intelligence_license`.** The consumer is bound by the license
   terms for any downstream use of the imported data, including fine-tuning,
   benchmarking, and re-export.

5. **Not backfill.** Do not use imported AIR data to make inferences about
   time periods before the bundle's `date_range.from`. The import event marks
   a new behavioral epoch.

6. **Degrade gracefully** using the following fallback hierarchy:
   1. Full rehydration — all components present and verified
   2. Fingerprint warm-start — trust starts at archetype prior, fingerprint
      seeds behavioral consistency scoring
   3. Org-context-only cold start — trust and fingerprint reset to archetype
      defaults, org vocabulary applied
   4. Bare cold start — treat as new agent; log a warning listing the
      components that failed verification

---

## Rehydration Guidance (Normative)

When importing a fingerprint component, a conformant platform:

- MUST preserve `total_observations` as recorded
- MUST apply a confidence decay factor: `imported_confidence = original_confidence × 0.85`
- SHOULD treat the imported fingerprint as the drift detection baseline for the
  new epoch

When importing a trust trajectory, a conformant platform:

- MUST use `current_score` as the starting trust score
- SHOULD cap the imported score at the platform's trust ceiling for new agents
  until the agent accumulates native observations
- MUST record the import event in the agent's trust trajectory with
  `"event": "air_import"`

When importing `knowledge_state`, a conformant platform:

- MUST record `distillation_method` alongside the insights
- SHOULD weight insights by their `confidence` value
- MAY ignore `embeddings` if the platform uses a different vector format

---

## CLI Commands

```bash
# Pack with full AIR bundle
agentpk pack ./my-agent --memory

# Pack with analysis and full AIR bundle
agentpk pack ./my-agent --analyze --memory

# Pack with selected components only
agentpk pack ./my-agent --memory --memory-components fingerprint,trust,org_context

# Valid component names
# audit | fingerprint | trust | org_context | knowledge_state
```

---

## Versioning

This is AIR v1.0. Breaking changes increment the major version.
Additive changes (new optional fields, new component types) increment
the minor version. The `air_version` field in every component file
records the spec version used at export time.

---

## License

This specification is licensed under CC BY 4.0.
Maintained by Nomotic AI at https://agentpk.io/specs/air
