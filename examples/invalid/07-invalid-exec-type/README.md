# Invalid Execution Type

The `execution.type` is set to `always-running`, which is not in the
allowed set: `scheduled`, `triggered`, `continuous`, `on-demand`.

Expected error (Stage 4 -- Consistency):
  ERROR: execution.type must be one of [...], got 'always-running'

Run: `agent pack .`
