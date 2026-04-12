# healthcare-agent-strict-redaction

A prior authorization agent demonstrating strict AIR redaction. This
package includes only `fingerprint` and `org_context` components — no
audit trail (excluded because strict redaction would collapse it to
useless records) and no knowledge state (operator chose not to export).

## Pack this example

```bash
agentpk pack examples/valid/healthcare-agent-strict-redaction --memory
agentpk inspect healthcare-agent-strict-redaction-1.0.0.agent
```

## What you'll see

The `redaction_profile` in the AIR bundle is `strict`. Only two
components are included: `fingerprint` and `org_context`. No PHI
appears in any exported file.

## The intelligence/ directory

- `air.json` — bundle manifest with strict redaction profile
- `fingerprint.json` — read-heavy behavioral profile (91% read, 9% write)
- `org_context.json` — HIPAA-specific vocabulary and escalation rules
