"""Tests for the agent signing module (agentpk.signing) — Ed25519."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from agentpk.cli import cli
from agentpk.packer import pack
from agentpk.signing import generate_keypair, sign_agent, verify_agent

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "valid"


@pytest.fixture()
def keypair(tmp_path: Path) -> tuple[Path, Path]:
    """Generate an Ed25519 key pair and return (private_key_path, public_key_path)."""
    private_path, public_path = generate_keypair(tmp_path / "test-key.pem")
    return private_path, public_path


@pytest.fixture()
def packed_agent(tmp_path: Path) -> Path:
    """Pack fraud-detection example and return path to .agent file."""
    src = EXAMPLES_DIR / "fraud-detection"
    out = tmp_path / "fraud-detection-0.1.0.agent"
    result = pack(src, output_path=out)
    assert result.success
    return out


class TestKeypairGeneration:
    """Tests for Ed25519 key generation."""

    def test_generates_two_files(self, keypair: tuple[Path, Path]) -> None:
        priv, pub = keypair
        assert priv.exists()
        assert pub.exists()

    def test_private_key_is_pem(self, keypair: tuple[Path, Path]) -> None:
        priv, _ = keypair
        assert priv.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")

    def test_public_key_is_pem(self, keypair: tuple[Path, Path]) -> None:
        _, pub = keypair
        assert pub.read_bytes().startswith(b"-----BEGIN PUBLIC KEY-----")

    def test_private_key_size_is_small(self, keypair: tuple[Path, Path]) -> None:
        # Ed25519 private key PEM should be well under 500 bytes
        # RSA-2048 would be ~1700 bytes — this confirms we're using Ed25519
        priv, _ = keypair
        assert len(priv.read_bytes()) < 500

    def test_public_key_suffix(self, tmp_path: Path) -> None:
        priv, pub = generate_keypair(tmp_path / "my-key.pem")
        assert pub.name == "my-key.pub.pem"


class TestSign:
    """Tests for Ed25519 signing."""

    def test_produces_sig_file(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        priv, _ = keypair
        sig_path = sign_agent(packed_agent, priv)
        assert sig_path.exists()
        assert sig_path.name == packed_agent.name + ".sig"

    def test_sig_is_valid_json(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        priv, _ = keypair
        sig_path = sign_agent(packed_agent, priv)
        data = json.loads(sig_path.read_text())
        assert "manifest_hash" in data
        assert "signature" in data
        assert "algorithm" in data
        assert data["algorithm"] == "ed25519"

    def test_sig_contains_expected_fields(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        priv, _ = keypair
        sig_path = sign_agent(packed_agent, priv)
        data = json.loads(sig_path.read_text())
        assert "manifest_hash" in data
        assert "signature" in data
        assert "signed_at" in data
        assert "algorithm" in data

    def test_signer_included(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        priv, _ = keypair
        sig_path = sign_agent(packed_agent, priv, signer="Acme AI")
        data = json.loads(sig_path.read_text())
        assert data.get("signer") == "Acme AI"


class TestVerify:
    """Tests for Ed25519 verification."""

    def test_valid_signature(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        priv, pub = keypair
        sign_agent(packed_agent, priv)
        valid, msg = verify_agent(packed_agent, pub)
        assert valid is True
        assert "not been modified" in msg

    def test_modified_agent_fails(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        priv, pub = keypair
        sign_agent(packed_agent, priv)

        # Tamper with the .agent file by modifying the manifest inside the archive
        import shutil
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            with zipfile.ZipFile(packed_agent, "r") as zf:
                zf.extractall(tmp_dir)
            # Modify manifest
            manifest = tmp_dir / "manifest.yaml"
            manifest.write_text(
                manifest.read_text().replace("fraud-detection", "fraud-tampered"),
                encoding="utf-8",
            )
            # Repack
            with zipfile.ZipFile(packed_agent, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(tmp_dir.rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(tmp_dir).as_posix())

        valid, msg = verify_agent(packed_agent, pub)
        assert valid is False

    def test_modified_sig_fails(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        priv, pub = keypair
        sig_path = sign_agent(packed_agent, priv)

        # Tamper with the signature hex
        data = json.loads(sig_path.read_text())
        data["signature"] = "00" * 64  # invalid 64-byte signature
        sig_path.write_text(json.dumps(data))

        valid, msg = verify_agent(packed_agent, pub)
        assert valid is False

    def test_missing_sig_fails(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        _, pub = keypair
        valid, msg = verify_agent(packed_agent, pub)
        assert valid is False
        assert "not found" in msg

    def test_wrong_key_returns_false(self, tmp_path: Path, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        priv, pub = keypair
        sign_agent(packed_agent, priv)

        # Generate a different keypair and try to verify
        _, pub2 = generate_keypair(tmp_path / "other-key.pem")
        valid, msg = verify_agent(packed_agent, pub2)
        assert valid is False


class TestKeygenCommand:
    """CLI tests for agent keygen."""

    def test_keygen_cli(self, tmp_path: Path) -> None:
        runner = CliRunner()
        key_path = tmp_path / "my-key.pem"
        result = runner.invoke(cli, ["keygen", "--out", str(key_path)])
        assert result.exit_code == 0
        assert key_path.exists()
        assert key_path.with_suffix(".pub.pem").exists()
        assert "Key pair generated" in result.output

    def test_keygen_refuses_overwrite(self, tmp_path: Path) -> None:
        runner = CliRunner()
        key_path = tmp_path / "my-key.pem"
        key_path.write_text("existing")
        result = runner.invoke(cli, ["keygen", "--out", str(key_path)])
        assert result.exit_code != 0
        # "already exists" may wrap across lines in Rich output
        combined = result.output.replace("\n", " ")
        assert "already exists" in combined


class TestSignVerifyRoundTrip:
    """CLI tests for the sign/verify round trip."""

    def test_sign_and_verify_cli(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        priv, pub = keypair
        runner = CliRunner()

        # Sign
        result = runner.invoke(cli, ["sign", str(packed_agent), "--key", str(priv)])
        assert result.exit_code == 0
        assert "Signed successfully" in result.output

        # Verify
        result = runner.invoke(cli, ["verify", str(packed_agent), "--key", str(pub)])
        assert result.exit_code == 0
        assert "Verification passed" in result.output
