# memory-malformed-air-json (invalid)

Demonstrates what happens when `air.json` is syntactically valid JSON
but missing required fields (`air_version` and `components`).

```bash
agentpk validate memory-malformed-air-json-1.0.0.agent
# -> ERROR: AIR bundle manifest invalid: required field 'air_version' missing
# -> ERROR: AIR bundle manifest invalid: required field 'components' missing
```
