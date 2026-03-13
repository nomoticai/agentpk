"""Cryptographic signing and verification for .agent files."""

from __future__ import annotations

import base64
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils
from cryptography.x509 import (
    CertificateBuilder,
    Name,
    NameAttribute,
    random_serial_number,
)
from cryptography.x509.oid import NameOID

from agentpk.constants import MANIFEST_FILENAME
from agentpk.manifest import compute_manifest_hash


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def generate_keypair(
    key_path: Path,
    cert_path: Path,
) -> None:
    """Generate an RSA-2048 private key and self-signed certificate.

    Args:
        key_path: Where to write the PEM-encoded private key.
        cert_path: Where to write the PEM-encoded certificate.
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Write private key
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    # Build self-signed certificate
    subject = issuer = Name([
        NameAttribute(NameOID.COMMON_NAME, "agentpk-signer"),
    ])

    import datetime as dt

    cert = (
        CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(random_serial_number())
        .not_valid_before(dt.datetime.now(dt.timezone.utc))
        .not_valid_after(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=3650))
        .sign(private_key, hashes.SHA256())
    )

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

def _extract_manifest_hash(agent_path: Path) -> str:
    """Compute the manifest hash from a packed .agent file."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        with zipfile.ZipFile(agent_path, "r") as zf:
            zf.extract(MANIFEST_FILENAME, tmp_dir)
        return compute_manifest_hash(tmp_dir / MANIFEST_FILENAME)


def sign_agent(
    agent_path: Path,
    key_path: Path,
    *,
    signer: Optional[str] = None,
    sig_path: Optional[Path] = None,
) -> Path:
    """Sign a .agent file and write a .sig file.

    Args:
        agent_path: Path to the .agent file to sign.
        key_path: Path to the PEM-encoded private key.
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
    private_key = serialization.load_pem_private_key(
        key_path.read_bytes(),
        password=None,
    )

    # Compute manifest hash
    manifest_hash = _extract_manifest_hash(agent_path)

    # Sign the hash bytes
    hash_bytes = manifest_hash.encode("utf-8")
    signature = private_key.sign(  # type: ignore[union-attr]
        hash_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )

    sig_data = {
        "agent": agent_path.name,
        "manifest_hash": manifest_hash,
        "algorithm": "RSA-PSS-SHA256",
        "signature": base64.b64encode(signature).decode("ascii"),
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
    cert_path: Path,
    *,
    sig_path: Optional[Path] = None,
) -> tuple[bool, str]:
    """Verify the signature on a .agent file.

    Args:
        agent_path: Path to the .agent file.
        cert_path: Path to the PEM-encoded certificate.
        sig_path: Path to the .sig file (default: <agent_path>.sig).

    Returns:
        (is_valid, message) tuple.
    """
    agent_path = agent_path.resolve()
    cert_path = cert_path.resolve()

    if sig_path is None:
        sig_path = agent_path.parent / (agent_path.name + ".sig")

    if not sig_path.exists():
        return False, f"Signature file not found: {sig_path}"

    # Load signature data
    try:
        sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"Failed to read signature file: {exc}"

    # Load certificate and extract public key
    try:
        cert = serialization.load_pem_public_key(cert_path.read_bytes())
    except Exception:
        # Try loading as an X.509 certificate instead
        from cryptography.x509 import load_pem_x509_certificate
        try:
            x509_cert = load_pem_x509_certificate(cert_path.read_bytes())
            cert = x509_cert.public_key()
        except Exception as exc:
            return False, f"Failed to load certificate: {exc}"

    # Re-compute manifest hash
    try:
        current_hash = _extract_manifest_hash(agent_path)
    except Exception as exc:
        return False, f"Failed to read agent file: {exc}"

    # Compare hashes
    stored_hash = sig_data.get("manifest_hash", "")
    if current_hash != stored_hash:
        return False, (
            "Manifest hash mismatch. The agent file has been modified since signing."
        )

    # Verify cryptographic signature
    signature = base64.b64decode(sig_data.get("signature", ""))
    hash_bytes = stored_hash.encode("utf-8")

    try:
        cert.verify(  # type: ignore[union-attr]
            signature,
            hash_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
    except Exception:
        return False, (
            "Signature verification failed. "
            "The agent file has been modified since it was signed."
        )

    return True, "Verified. Agent has not been modified since signing."
