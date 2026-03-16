"""Internal signing implementation for SDK."""

from __future__ import annotations

from pathlib import Path

from agentpk.sdk import AgentpkError


def run_sign(package: Path, *, key: Path, out: Path | None = None) -> Path:
    """Core sign implementation."""
    from agentpk.signing import sign_agent

    try:
        sig_path = sign_agent(package, key)
    except Exception as e:
        raise AgentpkError(f"Signing failed: {e}") from e

    return sig_path


def run_verify(package: Path, *, key: Path) -> bool:
    """Core verify implementation."""
    from agentpk.signing import verify_agent

    try:
        valid, message = verify_agent(package, key)
    except Exception as e:
        raise AgentpkError(f"Verification error: {e}") from e

    return valid
