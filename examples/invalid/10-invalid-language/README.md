# Invalid Language

The `runtime.language` is set to `cobol`, which is not in the allowed set:
`python`, `nodejs`, `typescript`, `go`, `rust`.

Expected error (Stage 4 -- Consistency):
  ERROR: runtime.language must be one of [...], got 'cobol'

Run: `agent pack .`
