# Manifest JSON Schema

`manifest.schema.json` is a [JSON Schema (draft-07)](http://json-schema.org/draft-07/schema#) for the `manifest.yaml` file inside `.agent` packages. It covers all manifest fields with types, enums, required markers, and descriptions. Point your editor at this schema to get autocomplete, inline validation, and hover documentation while editing agent manifests.

## VS Code setup

Install the [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) by Red Hat, then add the following to your `.vscode/settings.json`:

```json
{
  "yaml.schemas": {
    "./schema/manifest.schema.json": "manifest.yaml"
  }
}
```

This tells VS Code to apply the schema to any file named `manifest.yaml` in the workspace. You'll get autocomplete for field names, enum dropdowns for values like `language` and `scope`, and red squiggles for missing required fields.
