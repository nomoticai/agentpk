"""TypeScript signal extractor extending the Node.js extractor."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import StaticAnalysisFindings
from .nodejs_extractor import NodeJSExtractor


class TypeScriptExtractor(NodeJSExtractor):
    @property
    def language(self) -> str:
        return "typescript"

    @property
    def file_extensions(self) -> list[str]:
        return [".ts", ".tsx"]

    def _analyze_file(self, path: Path, findings: StaticAnalysisFindings) -> None:
        # Pass --typescript flag to js_ast_helper.js
        try:
            result = subprocess.run(
                ["node", str(self.HELPER), str(path), "--typescript"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                findings.extractor_warnings.append(f"{path.name}: {result.stderr[:200]}")
                return
            data = json.loads(result.stdout)
            self._merge(data, path, findings)
        except FileNotFoundError:
            findings.extractor_warnings.append("Node.js not found; TypeScript analysis unavailable")
        except Exception as e:
            findings.extractor_warnings.append(f"{path.name}: {e}")
