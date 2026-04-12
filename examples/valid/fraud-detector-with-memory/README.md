# fraud-detector-with-memory

A triggered financial agent demonstrating AIR (Agent Intelligence Record)
memory bundling. This package includes a full `intelligence/` directory
with behavioral fingerprint, trust trajectory, organizational context,
and distilled insights from 14 months of operation.

## Pack this example

```bash
agentpk pack examples/valid/fraud-detector-with-memory --memory
agentpk inspect fraud-detector-with-memory-1.0.0.agent
```

## What you'll see

The packed manifest will contain `_package.air` with the bundle
manifest. The `intelligence/` directory will be included in the archive.

Run `agentpk inspect` to see the AIR components listed alongside the
standard trust score and package metadata.

## The intelligence/ directory

- `air.json` — bundle manifest with component list and hashes
- `fingerprint.json` — behavioral profile from 4,721 observations
- `trust.json` — trust trajectory showing a drift event that recovered
- `org_context.json` — financial domain vocabulary and escalation rules
- `knowledge_state.json` — 4 distilled insights from operational history
