# CLI Reference

The `agent` command is the primary interface to agentpk. All commands use
[Rich](https://github.com/Textualize/rich) for coloured terminal output.

```
agent [OPTIONS] COMMAND [ARGS]...
```

Global options:

| Flag | Description |
|------|-------------|
| `--version` | Show the agentpk version and exit. |
| `--help` | Show help message and exit. |

---

## agent init

Scaffold a new agent project.

```bash
agent init <name>
agent init <name> -d <parent-directory>
agent init path/to/my-agent
```

Creates a directory with a `manifest.yaml`, entry point source file,
`requirements.txt`, `README.md`, and `.gitignore`.

| Argument / Flag | Description |
|-----------------|-------------|
| `NAME` | Project name. Must follow the naming rules (lowercase, hyphens, digits). Can include a path prefix (e.g. `agents/my-agent`). |
| `-d`, `--directory` | Parent directory for the new project. Default: current directory. |

---

## agent pack

Pack a directory into a `.agent` file.

```bash
agent pack <source>
agent pack <source> -o output.agent
agent pack <source> --out-dir ./dist/
agent pack <source> --dry-run
agent pack <source> --analyze
agent pack <source> --analyze --level 3 --strict
```

Validates the source directory, generates checksums, injects `_package`
metadata, creates a ZIP archive, and post-verifies the result.

| Argument / Flag | Description |
|-----------------|-------------|
| `SOURCE` | Path to the agent project directory. |
| `-o`, `--output` | Explicit output file path. |
| `--out-dir` | Output directory (filename auto-generated from name and version). |
| `--dry-run` | Validate and compute hashes without writing a file. |
| `-v`, `--verbose` | Show manifest and files hashes after packing. |
| `--strict` | Treat warnings as errors. When combined with `--analyze`, fails if the requested analysis level is not reached. |
| `--analyze` | Run code analysis before packing and embed a trust score. |
| `--level N` | Analysis depth 1-4. Default: highest available (auto-detects API keys and Docker). |
| `--on-discrepancy` | Behaviour when analysis finds undeclared capabilities: `warn` (default), `fail`, or `auto`. |

### Analysis flags

When `--analyze` is passed, agentpk runs the code analysis pipeline
before packing. The trust score and analysis metadata are embedded in the
`_package.analysis` block inside the archive.

Level auto-detection:

- Levels 1-2 always run (no external dependencies).
- Level 3 runs if `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set.
- Level 4 runs if Docker is available (not yet auto-detected; use `--level 4`).

See [agent_analyzer.md](agent_analyzer.md) for the full analysis
architecture.

---

## agent validate

Validate an agent directory or packed `.agent` file.

```bash
agent validate <target>
agent validate <target> --verbose
```

Runs the 6-stage validation pipeline. Directories skip stages 5-6
(checksums and package integrity) since those only apply to packed files.

| Argument / Flag | Description |
|-----------------|-------------|
| `TARGET` | Path to a project directory or `.agent` file. |
| `-v`, `--verbose` | Show a per-stage breakdown with pass/fail/skip status. |

### Validation stages

| Stage | Name | Applies to |
|-------|------|------------|
| 1 | Pre-flight | All |
| 2 | Identity | All |
| 3 | File presence | All |
| 4 | Consistency | All |
| 5 | Checksums | Packages only |
| 6 | Package integrity | Packages only |

---

## agent inspect

Display metadata from a packed `.agent` file.

```bash
agent inspect <agent-file>
```

Shows identity, runtime, capabilities, execution, package metadata,
trust score, file listing, and validation status.

| Argument | Description |
|----------|-------------|
| `AGENT_FILE` | Path to a `.agent` file. |

The trust score section shows the embedded analysis results if the
package was built with `--analyze`. Packages without analysis display
"unverified."

---

## agent unpack

Extract a `.agent` file to a directory.

```bash
agent unpack <agent-file>
agent unpack <agent-file> -d <destination>
```

Validates the package before extracting. Fails if validation does not
pass.

| Argument / Flag | Description |
|-----------------|-------------|
| `AGENT_FILE` | Path to a `.agent` file. |
| `-d`, `--dest` | Destination directory. Default: `<name>-<version>/` in the same directory as the `.agent` file. |

---

## agent diff

Show differences between two `.agent` files.

```bash
agent diff <old-file> <new-file>
```

Compares manifest fields and reports added, removed, and changed values.

| Argument | Description |
|----------|-------------|
| `OLD_FILE` | Path to the older `.agent` file. |
| `NEW_FILE` | Path to the newer `.agent` file. |

---

## agent generate

Generate a `manifest.yaml` from code analysis.

```bash
agent generate [directory]
agent generate ./my-agent --level 3
agent generate ./my-agent -o ./manifest.yaml
agent generate ./my-agent --force
```

Analyzes source code and produces a manifest based on what the code
actually does. Fields that cannot be determined from code analysis are
marked with `# REVIEW` comments.

If a `manifest.yaml` already exists, use `agent pack --analyze` to
verify it instead.

| Argument / Flag | Description |
|-----------------|-------------|
| `DIRECTORY` | Path to the agent source directory. Default: current directory. |
| `--level N` | Analysis level 1-4. Default: `2`. |
| `-o`, `--output` | Output path for the manifest file. Default: `manifest.yaml` inside the directory. |
| `-f`, `--force` | Overwrite an existing `manifest.yaml`. |

---

## agent list

List all `.agent` files in a directory.

```bash
agent list
agent list ./agents/
agent list ./agents/ --recursive
agent list ./agents/ --json
```

Scans for `.agent` files and displays a summary table with name,
version, execution type, tool count, and packaging date.

| Argument / Flag | Description |
|-----------------|-------------|
| `DIRECTORY` | Directory to scan. Default: current directory. |
| `-r`, `--recursive` | Walk subdirectories. |
| `--json` | Print machine-readable JSON instead of a Rich table. |

Invalid `.agent` files are included in the listing with a warning rather
than causing the command to fail.

---

## agent run

Execute a packed `.agent` file as a subprocess.

```bash
agent run <agent-file>
agent run <agent-file> --dry-run
agent run <agent-file> --keep
agent run <agent-file> --env API_KEY=abc123
agent run <agent-file> -- --flag value
```

Extracts the package to a temp directory, validates it, and launches the
entry point using the runtime declared in the manifest. Extra arguments
after `--` are forwarded to the agent process.

> **Warning:** `agent run` executes code from the package. Only run
> agents from sources you trust.

| Argument / Flag | Description |
|-----------------|-------------|
| `AGENT_FILE` | Path to a `.agent` file. |
| `--dry-run` | Validate and extract without executing. |
| `-k`, `--keep` | Keep the temp directory after execution. |
| `--env KEY=VALUE` | Set environment variables. Repeatable. |
| `-- [ARGS]` | Extra arguments forwarded to the agent process. |

---

## agent sign

Sign a `.agent` file with a private key.

```bash
agent sign <agent-file> --key <private-key.pem>
agent sign <agent-file> --key <private-key.pem> --signer "Acme AI"
```

Produces a `.sig` file alongside the `.agent` file. The signature file
is JSON containing the manifest hash, an RSA-PSS-SHA256 signature, and
optional signer metadata.

| Argument / Flag | Description |
|-----------------|-------------|
| `AGENT_FILE` | Path to a `.agent` file. |
| `--key` | **(required)** Path to a PEM-encoded RSA private key. |
| `--signer` | Optional signer identity string. |

---

## agent verify

Verify the signature on a `.agent` file.

```bash
agent verify <agent-file> --cert <certificate.pem>
```

Re-computes the manifest hash, compares it to the value in the `.sig`
file, and cryptographically verifies the signature against the
certificate. Fails if the agent or signature has been tampered with.

| Argument / Flag | Description |
|-----------------|-------------|
| `AGENT_FILE` | Path to a `.agent` file. |
| `--cert` | **(required)** Path to a PEM-encoded X.509 certificate. |

---

## agent keygen

Generate an RSA key pair for signing agents.

```bash
agent keygen --out <private-key.pem>
```

Creates two files:

- `<name>.pem` — RSA-2048 private key (keep secret)
- `<name>-cert.pem` — self-signed X.509 certificate (share with recipients)

| Flag | Description |
|------|-------------|
| `--out` | **(required)** Output path for the private key PEM file. The certificate is written alongside it with a `-cert` suffix. |

---

## agent test

Run built-in self-tests to verify the installation.

```bash
agent test
agent test --verbose
```

Generates 14 temporary agent fixtures (4 valid, 10 invalid), runs the
validation pipeline against each, and reports pass/fail results.

| Flag | Description |
|------|-------------|
| `-v`, `--verbose` | Show per-test detail. |

---

## Command summary

| Command | Description |
|---------|-------------|
| `agent init <name>` | Scaffold a new agent project |
| `agent pack <dir>` | Pack a directory into a `.agent` file |
| `agent validate <target>` | Validate a `.agent` file or project directory |
| `agent inspect <file>` | Display metadata from a `.agent` file |
| `agent unpack <file>` | Extract a `.agent` file to a directory |
| `agent diff <old> <new>` | Show differences between two `.agent` files |
| `agent generate [dir]` | Generate a manifest.yaml from code analysis |
| `agent list [dir]` | List all `.agent` files in a directory |
| `agent run <file>` | Execute a packed `.agent` file |
| `agent sign <file>` | Sign a `.agent` file with a private key |
| `agent verify <file>` | Verify the signature on a `.agent` file |
| `agent keygen` | Generate an RSA key pair for signing |
| `agent test` | Run built-in self-tests |

## Exit codes

All commands exit `0` on success and `1` on failure. Validation,
packing, and signing failures print errors to stderr.

## See also

- [Quickstart](quickstart.md) — get up and running
- [Configuration Reference](configuration.md) — full manifest.yaml schema
- [Code Analysis](agent_analyzer.md) — trust scores and analysis levels
