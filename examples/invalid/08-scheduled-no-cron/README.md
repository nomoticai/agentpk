# Scheduled Without Schedule

The `execution.type` is `scheduled` but the required `execution.schedule`
(cron expression) is missing.

Expected error (Stage 4 -- Consistency):
  ERROR: execution.schedule is required when type is 'scheduled'

Run: `agent pack .`
