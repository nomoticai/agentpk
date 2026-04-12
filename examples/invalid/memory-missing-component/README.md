# memory-missing-component (invalid)

Demonstrates what happens when air.json declares a component that is
not present in the archive.

`air.json` lists both `fingerprint` and `trust` as components, but
`intelligence/trust.json` is missing from the package.

```bash
agentpk validate memory-missing-component-1.0.0.agent
# -> ERROR: AIR bundle incomplete: declared component 'trust' not found
```
