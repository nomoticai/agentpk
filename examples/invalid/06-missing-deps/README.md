# Missing Dependencies File

The manifest declares `dependencies: requirements.txt` but the file does
not exist. Only `agent.py` is present.

Expected error (Stage 3 -- File presence):
  ERROR: Dependencies file not found: requirements.txt

Run: `agent pack .`
