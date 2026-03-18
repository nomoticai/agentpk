"""
agentpk signing — Ed25519

Agent packages are signed with Ed25519 private keys and verified with
the corresponding public keys. Ed25519 is the modern standard used by
SSH, Signal, Let's Encrypt, and Git.

Key format: raw PEM-encoded Ed25519 private/public keys.
Signature format: JSON .sig file alongside the .agent archive.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)

from agentpk.constants import MANIFEST_FILENAME
from agentpk.manifest import compute_manifest_hash


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def generate_keypair(private_key_path: Path) -> tuple[Path, Path]:
    """
    Generate an Ed25519 keypair.

    Args:
        private_key_path: Where to write the private key (e.g. my-key.pem)

    Returns:
        (private_key_path, public_key_path)
        Public key is written alongside private key as my-key.pub.pem
    """
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Write private key
    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    private_key_path.write_bytes(private_pem)

    # Write public key alongside private key
    public_key_path = private_key_path.with_suffix('.pub.pem')
    public_pem = public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )
    public_key_path.write_bytes(public_pem)

    return private_key_path, public_key_path


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

def _extract_manifest_hash(agent_path: Path) -> str:
    """Compute the manifest hash from a packed .agent file."""
    import tempfile
    import zipfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        with zipfile.ZipFile(agent_path, "r") as zf:
            zf.extract(MANIFEST_FILENAME, tmp_dir)
        return compute_manifest_hash(tmp_dir / MANIFEST_FILENAME)


def sign_agent(
    agent_path: Path,
    key_path: Path,
    *,
    signer: str | None = None,
    sig_path: Path | None = None,
) -> Path:
    """Sign a .agent file with an Ed25519 private key.

    Produces a .sig file containing the manifest hash, Ed25519 signature,
    algorithm identifier, and optional signer metadata.

    Args:
        agent_path: Path to the .agent file to sign.
        key_path: Path to Ed25519 private key (PEM).
        signer: Optional signer identity string.
        sig_path: Output .sig file path (default: <agent_path>.sig).

    Returns:
        Path to the written .sig file.
    """
    agent_path = agent_path.resolve()
    key_path = key_path.resolve()

    if sig_path is None:
        sig_path = agent_path.parent / (agent_path.name + ".sig")

    # Load private key
    private_key = load_pem_private_key(key_path.read_bytes(), password=None)

    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError(
            f"Key at {key_path} is not an Ed25519 private key. "
            f"Generate a new keypair with: agent keygen --out {key_path}"
        )

    # Compute manifest hash
    manifest_hash = _extract_manifest_hash(agent_path)

    # Sign the hash bytes
    message = manifest_hash.encode("utf-8")
    signature_bytes = private_key.sign(message)
    signature_hex = signature_bytes.hex()

    sig_data = {
        "agent": agent_path.name,
        "manifest_hash": manifest_hash,
        "algorithm": "ed25519",
        "signature": signature_hex,
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }

    if signer:
        sig_data["signer"] = signer

    sig_path.write_text(
        json.dumps(sig_data, indent=2) + "\n",
        encoding="utf-8",
    )

    return sig_path


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_agent(
    agent_path: Path,
    public_key_path: Path,
    *,
    sig_path: Path | None = None,
) -> tuple[bool, str]:
    """Verify the Ed25519 signature on a .agent file.

    Args:
        agent_path: Path to the .agent file.
        public_key_path: Path to Ed25519 public key (PEM, .pub.pem).
        sig_path: Path to the .sig file (default: <agent_path>.sig).

    Returns:
        (is_valid, message) tuple.
    """
    from cryptography.exceptions import InvalidSignature

    agent_path = agent_path.resolve()
    public_key_path = public_key_path.resolve()

    if sig_path is None:
        sig_path = agent_path.parent / (agent_path.name + ".sig")

    if not sig_path.exists():
        return False, f"Signature file not found: {sig_path}"

    # Load signature data
    try:
        sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"Failed to read signature file: {exc}"

    algorithm = sig_data.get("algorithm")
    if algorithm != "ed25519":
        return False, (
            f"Unsupported signature algorithm: {algorithm!r}. "
            f"This package was signed with an older version of agentpk. "
            f"Re-sign with: agent sign {agent_path}"
        )

    stored_hash = sig_data.get("manifest_hash", "")
    signature_hex = sig_data.get("signature", "")

    # Re-compute manifest hash
    try:
        current_hash = _extract_manifest_hash(agent_path)
    except Exception as exc:
        return False, f"Failed to read agent file: {exc}"

    # Compare hashes — fast fail
    if current_hash != stored_hash:
        return False, (
            "Manifest hash mismatch. The agent file has been modified since signing."
        )

    # Load public key
    try:
        public_key = load_pem_public_key(public_key_path.read_bytes())
    except Exception as exc:
        return False, f"Failed to load public key: {exc}"

    if not isinstance(public_key, Ed25519PublicKey):
        return False, (
            f"Key at {public_key_path} is not an Ed25519 public key."
        )

    # Verify signature
    try:
        signature_bytes = bytes.fromhex(signature_hex)
        message = stored_hash.encode("utf-8")
        public_key.verify(signature_bytes, message)
    except InvalidSignature:
        return False, (
            "Signature verification failed. "
            "The agent file has been modified since it was signed."
        )
    except Exception as exc:
        return False, f"Signature verification error: {exc}"

    return True, "Verified. Agent has not been modified since signing."
