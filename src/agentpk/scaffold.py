"""Project scaffolding for ``agent init``."""

from __future__ import annotations

from pathlib import Path

from agentpk.constants import FORMAT_VERSION

# ---------------------------------------------------------------------------
# Template content — Python (default)
# ---------------------------------------------------------------------------

_MANIFEST_TEMPLATE = """\
spec_version: "{spec_version}"
name: {name}
version: "0.1.0"
description: "TODO: Describe what this agent does."
runtime:
  language: {language}
  language_version: "{language_version}"
  entry_point: {entry_point}
  entry_function: {entry_function}
  dependencies: {dependencies}
capabilities:
  tools: []
execution:
  type: on-demand
"""

_AGENT_PY = """\
\"\"\"Agent entry point.\"\"\"


def main() -> None:
    \"\"\"Run the agent.\"\"\"
    # TODO: implement your agent logic here
    print("Hello from {name}!")


if __name__ == "__main__":
    main()
"""

_INIT_PY = """\
\"\"\"Agent source package.\"\"\"
"""

_REQUIREMENTS = """\
# Add your agent's Python dependencies here, one per line.
# Example:
# requests>=2.28
# pydantic>=2.0
"""

# ---------------------------------------------------------------------------
# Template content — Node.js
# ---------------------------------------------------------------------------

_AGENT_JS = """\
/**
 * Agent entry point.
 */

async function run() {{
  // TODO: implement your agent logic here
  console.log("Hello from {name}!");
}}

module.exports = {{ run }};

if (require.main === module) {{
  run();
}}
"""

_PACKAGE_JSON = """\
{{
  "name": "{name}",
  "version": "0.1.0",
  "description": "TODO: Describe what this agent does.",
  "main": "agent.js",
  "scripts": {{
    "start": "node agent.js"
  }},
  "dependencies": {{}}
}}
"""

# ---------------------------------------------------------------------------
# Template content — TypeScript
# ---------------------------------------------------------------------------

_AGENT_TS = """\
/**
 * Agent entry point.
 */

export async function run(): Promise<void> {{
  // TODO: implement your agent logic here
  console.log("Hello from {name}!");
}}

if (require.main === module) {{
  run();
}}
"""

_TSCONFIG_JSON = """\
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "strict": true,
    "outDir": "./dist",
    "rootDir": "./",
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["*.ts"]
}
"""

# ---------------------------------------------------------------------------
# Template content — Go
# ---------------------------------------------------------------------------

_MAIN_GO = """\
package main

import "fmt"

func main() {{
\t// TODO: implement your agent logic here
\tfmt.Println("Hello from {name}!")
}}
"""

_GO_MOD = """\
module {name}

go 1.21
"""

# ---------------------------------------------------------------------------
# Template content — Java
# ---------------------------------------------------------------------------

_AGENT_JAVA = """\
/**
 * Agent entry point.
 */
public class Agent {{
    public static void main(String[] args) {{
        // TODO: implement your agent logic here
        System.out.println("Hello from {name}!");
    }}

    public void run() {{
        main(new String[]{{}});
    }}
}}
"""

_POM_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>{name}</artifactId>
    <version>0.1.0</version>
    <packaging>jar</packaging>
    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
    </properties>
</project>
"""

# ---------------------------------------------------------------------------
# Common templates
# ---------------------------------------------------------------------------

_README = """\
# {name}

TODO: Describe your agent.

## Quick start

```bash
# Pack into a .agent file
agent pack .

# Validate the package
agent validate {name}-0.1.0.agent
```
"""

_GITIGNORE_PYTHON = """\
*.agent
__pycache__/
*.py[cod]
.venv/
"""

_GITIGNORE_NODE = """\
*.agent
node_modules/
dist/
"""

_GITIGNORE_GO = """\
*.agent
bin/
"""

_GITIGNORE_JAVA = """\
*.agent
target/
*.class
"""

# ---------------------------------------------------------------------------
# Runtime configurations
# ---------------------------------------------------------------------------

_RUNTIME_CONFIGS = {
    "python": {
        "language": "python",
        "language_version": "3.11",
        "entry_point": "src/agent.py",
        "entry_function": "main",
        "dependencies": "requirements.txt",
    },
    "nodejs": {
        "language": "nodejs",
        "language_version": "20",
        "entry_point": "agent.js",
        "entry_function": "run",
        "dependencies": "package.json",
    },
    "typescript": {
        "language": "typescript",
        "language_version": "20",
        "entry_point": "agent.ts",
        "entry_function": "run",
        "dependencies": "package.json",
    },
    "go": {
        "language": "go",
        "language_version": "1.21",
        "entry_point": "main.go",
        "entry_function": "main",
        "dependencies": "go.mod",
    },
    "java": {
        "language": "java",
        "language_version": "17",
        "entry_point": "Agent.java",
        "entry_function": "main",
        "dependencies": "pom.xml",
    },
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scaffold(project_name: str, output_dir: Path, runtime: str = "python") -> list[str]:
    """Create a new agent project at *output_dir* / *project_name*.

    Returns a list of created file paths (relative to the project root).
    """
    project_dir = output_dir / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    files_created: list[str] = []

    def _write(rel: str, content: str) -> None:
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        files_created.append(rel)

    # Get runtime config
    rt = _RUNTIME_CONFIGS.get(runtime, _RUNTIME_CONFIGS["python"])

    # Write manifest
    _write(
        "manifest.yaml",
        _MANIFEST_TEMPLATE.format(
            spec_version=FORMAT_VERSION,
            name=project_name,
            **rt,
        ),
    )

    # Write language-specific files
    if runtime == "python":
        (project_dir / "src").mkdir(exist_ok=True)
        _write("src/__init__.py", _INIT_PY)
        _write("src/agent.py", _AGENT_PY.format(name=project_name))
        _write("requirements.txt", _REQUIREMENTS)
        _write(".gitignore", _GITIGNORE_PYTHON)
    elif runtime == "nodejs":
        _write("agent.js", _AGENT_JS.format(name=project_name))
        _write("package.json", _PACKAGE_JSON.format(name=project_name))
        _write(".gitignore", _GITIGNORE_NODE)
    elif runtime == "typescript":
        _write("agent.ts", _AGENT_TS.format(name=project_name))
        _write("package.json", _PACKAGE_JSON.format(name=project_name))
        _write("tsconfig.json", _TSCONFIG_JSON)
        _write(".gitignore", _GITIGNORE_NODE)
    elif runtime == "go":
        _write("main.go", _MAIN_GO.format(name=project_name))
        _write("go.mod", _GO_MOD.format(name=project_name))
        _write(".gitignore", _GITIGNORE_GO)
    elif runtime == "java":
        _write("Agent.java", _AGENT_JAVA.format(name=project_name))
        _write("pom.xml", _POM_XML.format(name=project_name))
        _write(".gitignore", _GITIGNORE_JAVA)

    _write("README.md", _README.format(name=project_name))

    return files_created
