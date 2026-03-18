"""Internal signing implementation for SDK — Ed25519."""

from __future__ import annotations

from pathlib import Path

from agentpk.sdk import AgentpkError


def run_sign(
    package: Path,
    *,
    key: Path,
    signer: str | None = None,
    out: Path | None = None,
) -> Path:
    """Core sign implementation using Ed25519."""
    from agentpk.signing import sign_agent

    try:
        sig_path = sign_agent(package, key, signer=signer, sig_path=out)
    except Exception as e:
        raise AgentpkError(f"Signing failed: {e}") from e

    return sig_path


def run_verify(package: Path, *, key: Path) -> bool:
    """Core verify implementation using Ed25519."""
    from agentpk.signing import verify_agent

    try:
        valid, message = verify_agent(package, key)
    except Exception as e:
        raise AgentpkError(f"Verification error: {e}") from e

    return valid
