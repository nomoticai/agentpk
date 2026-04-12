# memory-hash-mismatch (invalid)

Demonstrates AIR bundle hash verification failure.

The `intelligence/air.json` declares a hash for `fingerprint.json` that
does not match the actual file content.

Expected behavior: `agentpk validate` should report the hash mismatch
and reject the package. `agentpk inspect` should display a tamper warning.

```bash
agentpk validate memory-hash-mismatch-1.0.0.agent
# -> ERROR: AIR bundle verification failed: fingerprint component hash mismatch
```
