# Environment Variable Overlap

The variable `STAGING_HOST` appears in both `permissions.environments.allowed`
and `permissions.environments.denied`.

Expected error (Stage 4 -- Consistency):
  ERROR: environments.allowed and environments.denied overlap: {'STAGING_HOST'}

Run: `agent pack .`
