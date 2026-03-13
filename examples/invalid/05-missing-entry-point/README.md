# Missing Entry Point

The manifest declares `entry_point: agent.py` but the file does not exist.
Only `requirements.txt` is present.

Expected error (Stage 3 -- File presence):
  ERROR: Entry-point file not found: agent.py

Run: `agent pack .`
