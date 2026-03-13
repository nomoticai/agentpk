# Invalid Tool Scope

A tool declares `scope: superuser` which is not in the allowed set:
`read`, `write`, `execute`, `delete`, `admin`.

Expected error (Stage 4 -- Consistency):
  ERROR: Tool super-tool: scope must be one of [...], got 'superuser'

Run: `agent pack .`
