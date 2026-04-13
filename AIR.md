# Agent Intelligence Record (AIR) Specification

**Version:** 1.1
**Status:** Draft
**Spec URL:** https://agentpk.io/specs/air/v1.1
**License:** CC BY 4.0

---

## Overview

The Agent Intelligence Record (AIR) is an open, schema-defined standard for
portable agent memory. An AIR bundle captures the operational intelligence an
agent has accumulated -- its behavioral history, statistical profile, trust
trajectory, organizational knowledge, compliance posture, domain understanding,
interaction patterns, and distilled insights -- in a format any platform can
consume without requiring the issuing platform.

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
    ├── air.json                 ← manifest (required)
    ├── audit.jsonl              ← transaction history (optional)
    ├── fingerprint.json         ← behavioral profile (optional)
    ├── trust.json               ← trust trajectory (optional)
    ├── org_context.json         ← organizational knowledge (optional)
    ├── compliance_state.json    ← regulatory posture (optional)
    ├── domain_model.json        ← learned domain understanding (optional)
    ├── interaction_patterns.json ← learned interaction patterns (optional)
    └── knowledge_state.json     ← distilled insights (optional)
```

The `air.json` manifest is the only required file. All component files are
optional. A bundle with only `air.json` is valid; it declares the agent's
identity and export provenance with no behavioral data.

---

## Architecture: Three Layers

AIR bundles are organized into three explicit layers. Each layer is
independent -- a bundle may contain components from one, two, or all
three layers depending on what was available at export time.

### Layer 1 -- Governance Record
What happened and what governance decided. Produced automatically by
any Nomotic-governed agent.

| Component | File |
|-----------|------|
| Audit trail | `audit.jsonl` + `audit.json` manifest |
| Behavioral fingerprint | `fingerprint.json` |
| Trust trajectory | `trust.json` |

### Layer 2 -- Institutional Context
What the organization defined. Configured in Nomotic's Context and
Governance modules.

| Component | File |
|-----------|------|
| Organizational context | `org_context.json` |
| Compliance state | `compliance_state.json` |

### Layer 3 -- Operational Intelligence
What the agent learned through experience. Derived from operational
history, not from governance rules.

| Component | File |
|-----------|------|
| Domain model | `domain_model.json` |
| Interaction patterns | `interaction_patterns.json` |
| Knowledge state | `knowledge_state.json` |

---

## Components

### `air.json` -- Bundle Manifest (required)

```json
{
  "air_version": "1.1",
  "spec": "https://agentpk.io/specs/air/v1.1",
  "agent_id": "string",
  "certificate_id": "string | null",
  "issuing_platform": "string",
  "issuing_platform_version": "string",
  "export_timestamp": "ISO 8601",
  "components": ["audit", "fingerprint", "trust", "org_context", "compliance_state", "domain_model", "interaction_patterns", "knowledge_state"],
  "component_hashes": {
    "audit": "sha256:...",
    "fingerprint": "sha256:...",
    "trust": "sha256:...",
    "org_context": "sha256:...",
    "compliance_state": "sha256:...",
    "domain_model": "sha256:...",
    "interaction_patterns": "sha256:...",
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
  },
  "layer_summary": {
    "governance_record": true,
    "institutional_context": true,
    "operational_intelligence": true
  }
}
```

`component_hashes` lists only components present in the bundle. Components
listed in `components` but absent from the archive are a conformance error.

`intelligence_license.default` applies to all components not listed under
`intelligence_license.components`. Per-component values override the default.

`export_sig` is an Ed25519 signature over the canonical JSON serialization of
`air.json` with `export_sig` set to `null`. Optional but recommended.

`layer_summary` indicates which of the three layers have at least one
component present. Optional but recommended for quick filtering.

---

### `audit.jsonl` -- Transaction History

Hash-chained audit records in newline-delimited JSON. Each line is one record.

```json
{"seq": 1, "ts": "ISO 8601", "action": "string", "verdict": "ALLOW|DENY|ESCALATE", "hash": "sha256:...", "prev_hash": "sha256:..."}
```

The first record has `"prev_hash": "genesis"`. Each record's `hash` is
SHA-256 of the canonical JSON of the record with `hash` set to `null`.

**Manifest fields:**

```json
{
  "air_version": "1.1",
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
- `minimal` -- removes free-text fields only
- `standard` -- removes PII identifiers, keeps statistical shape
- `strict` -- retains only verdict, timestamp, and hash per record

---

### `fingerprint.json` -- Behavioral Profile

Statistical description of the agent's action patterns.

```json
{
  "air_version": "1.1",
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

### `trust.json` -- Trust Trajectory

Time-series of trust score changes with labeled events.

```json
{
  "air_version": "1.1",
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

### `org_context.json` -- Organizational Knowledge

Institutional context that makes the agent specific to an organization.

```json
{
  "air_version": "1.1",
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

### `compliance_state.json` -- Regulatory Posture (new in v1.1)

Snapshot of the regulatory frameworks, governance policies, and data
classifications in effect at export time. Allows a receiving platform
to understand the compliance context before applying governance.

```json
{
  "air_version": "1.1",
  "snapshot_timestamp": "ISO 8601",
  "active_frameworks": [
    {
      "name": "HIPAA",
      "version": "2013 Omnibus Rule",
      "status": "active",
      "effective_from": "ISO 8601",
      "policy_version": "string",
      "notes": "string"
    }
  ],
  "policy_snapshots": [
    {
      "policy_id": "string",
      "version": "string",
      "active_from": "ISO 8601",
      "hash": "sha256:..."
    }
  ],
  "data_classifications": [
    {
      "classification": "PHI | PII | PCI | confidential | public",
      "access_level": "read | write | admin",
      "authorized_from": "ISO 8601"
    }
  ],
  "audit_retention_policy": {
    "retention_days": 2555,
    "legal_hold": false
  }
}
```

---

### `domain_model.json` -- Learned Domain Understanding (new in v1.1)

The agent's learned understanding of its operational domain -- entities,
relationships, edge cases, and calibrated thresholds discovered through
experience rather than configuration.

```json
{
  "air_version": "1.1",
  "snapshot_timestamp": "ISO 8601",
  "domain": "fraud-detection",
  "entities": [
    {
      "id": "ent-001",
      "name": "high-value-transaction",
      "description": "string",
      "confidence": 0.97,
      "observation_count": 8420,
      "attributes": ["amount", "merchant_category"]
    }
  ],
  "learned_thresholds": [
    {
      "parameter": "high_value_amount_usd",
      "learned_value": 8500,
      "default_value": 10000,
      "confidence": 0.92,
      "sample_size": 8420,
      "rationale": "string"
    }
  ],
  "edge_cases": [
    {
      "id": "ec-001",
      "description": "string",
      "resolution": "string",
      "frequency": 34,
      "first_observed": "ISO 8601",
      "confidence": 0.95
    }
  ],
  "terminology": {
    "term_name": {
      "definition": "string",
      "context": "string",
      "confidence": 0.99
    }
  }
}
```

---

### `interaction_patterns.json` -- Learned Interaction Patterns (new in v1.1)

Learned patterns about the humans and systems the agent works with --
request types, ambiguity resolutions, communication preferences, and
system integration quirks.

```json
{
  "air_version": "1.1",
  "snapshot_timestamp": "ISO 8601",
  "total_interactions": 14382,
  "request_patterns": [
    {
      "pattern_id": "rp-001",
      "description": "string",
      "frequency": 12140,
      "typical_resolution": "string",
      "avg_confidence": 0.94,
      "escalation_rate": 0.05
    }
  ],
  "ambiguity_resolutions": [
    {
      "scenario": "string",
      "learned_resolution": "string",
      "confidence": 0.90,
      "sample_count": 284,
      "override_rate": 0.03
    }
  ],
  "communication_preferences": {
    "verbosity": "minimal | standard | detailed",
    "escalation_preference": "conservative | balanced | aggressive",
    "confirmation_threshold": 0.85
  },
  "system_integrations": [
    {
      "system_id": "string",
      "system_type": "string",
      "interaction_count": 12140,
      "success_rate": 0.998,
      "learned_quirks": ["string"]
    }
  ]
}
```

---

### `knowledge_state.json` -- Distilled Insights (optional)

Structured summary of what the agent has come to know, distilled from
operational history. This is derived intelligence, not raw history.

```json
{
  "air_version": "1.1",
  "snapshot_timestamp": "ISO 8601",
  "distillation_method": "nomotic-v1 | manual | external",
  "summary_count": 142,
  "key_insights": [
    {
      "id": "ki-001",
      "domain": "escalation_patterns",
      "content": "string",
      "confidence": 0.91,
      "insight_source": "governance_derived | experience_derived | human_annotated | hybrid",
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
an empty array. `distillation_method` is required -- consuming platforms
use it to calibrate how much to trust the insights.

`insight_source` (new in v1.1) indicates whether each insight was derived
from governance patterns, operational experience, human annotation, or a
combination. Receiving platforms SHOULD weight `governance_derived` insights
higher than `experience_derived` since governance data has a verifiable
audit chain.

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

6. **Record `active_frameworks` from `compliance_state`** before applying
   governance to the imported agent. The receiving platform must be aware
   of which regulatory frameworks were in effect at the exporting platform
   to ensure continuity of compliance posture.

7. **Treat `insight_source` on knowledge_state insights as a trust signal.**
   `governance_derived` insights are more verifiable than `experience_derived`
   because they originate from an auditable governance chain. Receiving
   platforms SHOULD weight them accordingly.

8. **Degrade gracefully** using the following fallback hierarchy:
   1. Full rehydration -- all components present and verified
   2. Fingerprint warm-start -- trust starts at archetype prior, fingerprint
      seeds behavioral consistency scoring
   3. Org-context-only cold start -- trust and fingerprint reset to archetype
      defaults, org vocabulary applied
   4. Bare cold start -- treat as new agent; log a warning listing the
      components that failed verification

---

## Rehydration Guidance (Normative)

When importing a fingerprint component, a conformant platform:

- MUST preserve `total_observations` as recorded
- MUST apply a confidence decay factor: `imported_confidence = original_confidence x 0.85`
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
- SHOULD use `insight_source` to apply differential trust weighting
- MAY ignore `embeddings` if the platform uses a different vector format

When importing `compliance_state`, a conformant platform:

- MUST record all `active_frameworks` before applying local governance
- SHOULD alert operators if any `active` framework at export time is not
  supported by the receiving platform
- MUST preserve `data_classifications` and apply at least equivalent access
  controls

When importing `domain_model`, a conformant platform:

- SHOULD treat `learned_thresholds` as suggestions, not overrides
- SHOULD present `edge_cases` to operators for review before activation
- MAY merge `terminology` with local domain vocabulary

When importing `interaction_patterns`, a conformant platform:

- SHOULD use `communication_preferences` as initial defaults, adjustable
  through local experience
- SHOULD record `learned_quirks` from system integrations but verify
  applicability in the new environment

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
# audit | fingerprint | trust | org_context | compliance_state
# domain_model | interaction_patterns | knowledge_state
```

---

## Versioning

This is AIR v1.1. Breaking changes increment the major version.
Additive changes (new optional fields, new component types) increment
the minor version. The `air_version` field in every component file
records the spec version used at export time.

### Changes in v1.1
- Added `compliance_state` component (Layer 2)
- Added `domain_model` component (Layer 3)
- Added `interaction_patterns` component (Layer 3)
- Added `insight_source` required field to `knowledge_state` insights
- Added `layer_summary` optional field to `air.json` manifest
- Organized components into three explicit layers

---

## License

This specification is licensed under CC BY 4.0.
Maintained by Nomotic AI at https://agentpk.io/specs/air
