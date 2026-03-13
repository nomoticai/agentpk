"""Tests for the agent signing module (agentpk.signing)."""

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
    """Generate a key pair and return (key_path, cert_path)."""
    key_path = tmp_path / "test-key.pem"
    cert_path = tmp_path / "test-cert.pem"
    generate_keypair(key_path, cert_path)
    return key_path, cert_path


@pytest.fixture()
def packed_agent(tmp_path: Path) -> Path:
    """Pack fraud-detection example and return path to .agent file."""
    src = EXAMPLES_DIR / "fraud-detection"
    out = tmp_path / "fraud-detection-0.1.0.agent"
    result = pack(src, output_path=out)
    assert result.success
    return out


class TestKeygen:
    """Tests for key generation."""

    def test_generates_key_and_cert(self, keypair: tuple[Path, Path]) -> None:
        key_path, cert_path = keypair
        assert key_path.exists()
        assert cert_path.exists()

    def test_key_is_pem(self, keypair: tuple[Path, Path]) -> None:
        key_path, _ = keypair
        content = key_path.read_text()
        assert "BEGIN RSA PRIVATE KEY" in content

    def test_cert_is_pem(self, keypair: tuple[Path, Path]) -> None:
        _, cert_path = keypair
        content = cert_path.read_text()
        assert "BEGIN CERTIFICATE" in content


class TestSign:
    """Tests for signing."""

    def test_produces_sig_file(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        key_path, _ = keypair
        sig_path = sign_agent(packed_agent, key_path)
        assert sig_path.exists()
        assert sig_path.name == packed_agent.name + ".sig"

    def test_sig_is_valid_json(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        key_path, _ = keypair
        sig_path = sign_agent(packed_agent, key_path)
        data = json.loads(sig_path.read_text())
        assert "manifest_hash" in data
        assert "signature" in data
        assert "algorithm" in data
        assert data["algorithm"] == "RSA-PSS-SHA256"

    def test_signer_included(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        key_path, _ = keypair
        sig_path = sign_agent(packed_agent, key_path, signer="Test Signer")
        data = json.loads(sig_path.read_text())
        assert data.get("signer") == "Test Signer"


class TestVerify:
    """Tests for verification."""

    def test_valid_signature(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        key_path, cert_path = keypair
        sign_agent(packed_agent, key_path)
        valid, msg = verify_agent(packed_agent, cert_path)
        assert valid is True
        assert "not been modified" in msg

    def test_modified_agent_fails(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        key_path, cert_path = keypair
        sign_agent(packed_agent, key_path)

        # Tamper with the .agent file by modifying the manifest inside the ZIP
        import zipfile
        import tempfile
        import shutil
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

        valid, msg = verify_agent(packed_agent, cert_path)
        assert valid is False

    def test_modified_sig_fails(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        key_path, cert_path = keypair
        sig_path = sign_agent(packed_agent, key_path)

        # Tamper with the .sig file
        data = json.loads(sig_path.read_text())
        data["signature"] = "dGFtcGVyZWQ="  # base64("tampered")
        sig_path.write_text(json.dumps(data))

        valid, msg = verify_agent(packed_agent, cert_path)
        assert valid is False

    def test_missing_sig_fails(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        _, cert_path = keypair
        valid, msg = verify_agent(packed_agent, cert_path)
        assert valid is False
        assert "not found" in msg


class TestKeygenCommand:
    """CLI tests for agent keygen."""

    def test_keygen_cli(self, tmp_path: Path) -> None:
        runner = CliRunner()
        key_path = tmp_path / "my-key.pem"
        result = runner.invoke(cli, ["keygen", "--out", str(key_path)])
        assert result.exit_code == 0
        assert key_path.exists()
        assert "Key pair generated" in result.output


class TestSignVerifyRoundTrip:
    """CLI tests for the sign/verify round trip."""

    def test_sign_and_verify_cli(self, packed_agent: Path, keypair: tuple[Path, Path]) -> None:
        key_path, cert_path = keypair
        runner = CliRunner()

        # Sign
        result = runner.invoke(cli, ["sign", str(packed_agent), "--key", str(key_path)])
        assert result.exit_code == 0
        assert "Signed successfully" in result.output

        # Verify
        result = runner.invoke(cli, ["verify", str(packed_agent), "--cert", str(cert_path)])
        assert result.exit_code == 0
        assert "Verification passed" in result.output
