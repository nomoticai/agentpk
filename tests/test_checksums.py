"""Tests for agentpk.checksums."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentpk.checksums import (
    compute_file_hash,
    compute_files_hash,
    generate_checksums,
    read_checksums_file,
    verify_checksums,
    write_checksums_file,
)
from agentpk.constants import CHECKSUMS_FILENAME


# ── helpers ────────────────────────────────────────────────────────────────


def _populate(tmp_path: Path) -> Path:
    """Create a small directory tree and return its root."""
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("bravo", encoding="utf-8")
    return tmp_path


# ── compute_file_hash ─────────────────────────────────────────────────────


class TestComputeFileHash:
    def test_deterministic(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello", encoding="utf-8")
        h1 = compute_file_hash(f)
        h2 = compute_file_hash(f)
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_different_content_differs(self, tmp_path: Path) -> None:
        f1 = tmp_path / "one.txt"
        f1.write_text("one", encoding="utf-8")
        f2 = tmp_path / "two.txt"
        f2.write_text("two", encoding="utf-8")
        assert compute_file_hash(f1) != compute_file_hash(f2)


# ── compute_files_hash ────────────────────────────────────────────────────


class TestComputeFilesHash:
    def test_deterministic(self, tmp_path: Path) -> None:
        root = _populate(tmp_path)
        paths = list(root.rglob("*"))
        paths = [p for p in paths if p.is_file()]
        h1 = compute_files_hash(paths, root)
        h2 = compute_files_hash(paths, root)
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_order_independent(self, tmp_path: Path) -> None:
        root = _populate(tmp_path)
        paths = sorted(root.rglob("*"))
        paths = [p for p in paths if p.is_file()]
        h_fwd = compute_files_hash(paths, root)
        h_rev = compute_files_hash(list(reversed(paths)), root)
        assert h_fwd == h_rev


# ── generate_checksums ────────────────────────────────────────────────────


class TestGenerateChecksums:
    def test_generates_sha256_for_all_files(self, tmp_path: Path) -> None:
        root = _populate(tmp_path)
        checksums = generate_checksums(root)
        assert "a.txt" in checksums
        assert "sub/b.txt" in checksums
        assert all(v.startswith("sha256:") for v in checksums.values())

    def test_excludes_checksums_file_itself(self, tmp_path: Path) -> None:
        root = _populate(tmp_path)
        (root / CHECKSUMS_FILENAME).write_text("placeholder", encoding="utf-8")
        checksums = generate_checksums(root)
        assert CHECKSUMS_FILENAME not in checksums

    def test_custom_exclude(self, tmp_path: Path) -> None:
        root = _populate(tmp_path)
        checksums = generate_checksums(root, exclude=["a.txt"])
        assert "a.txt" not in checksums
        assert "sub/b.txt" in checksums


# ── write / read checksums file ───────────────────────────────────────────


class TestWriteAndReadChecksumsFile:
    def test_writes_valid_format(self, tmp_path: Path) -> None:
        checksums = {
            "a.txt": "sha256:abc123",
            "sub/b.txt": "sha256:def456",
        }
        out = tmp_path / CHECKSUMS_FILENAME
        write_checksums_file(checksums, out)
        raw = out.read_text(encoding="utf-8")
        lines = raw.strip().splitlines()
        assert len(lines) == 2
        # Lines should be sorted by path
        assert lines[0].startswith("abc123  a.txt")
        assert lines[1].startswith("def456  sub/b.txt")

    def test_roundtrip(self, tmp_path: Path) -> None:
        root = _populate(tmp_path)
        original = generate_checksums(root)

        out = tmp_path / CHECKSUMS_FILENAME
        write_checksums_file(original, out)
        parsed = read_checksums_file(out)

        assert parsed == original

    def test_read_ignores_blank_lines(self, tmp_path: Path) -> None:
        out = tmp_path / CHECKSUMS_FILENAME
        out.write_text(
            "abc123  a.txt\n\ndef456  b.txt\n\n", encoding="utf-8"
        )
        parsed = read_checksums_file(out)
        assert len(parsed) == 2


# ── verify_checksums ──────────────────────────────────────────────────────


class TestVerifyChecksums:
    def test_valid_checksums_pass(self, tmp_path: Path) -> None:
        root = _populate(tmp_path)
        checksums = generate_checksums(root)
        cf = root / CHECKSUMS_FILENAME
        write_checksums_file(checksums, cf)

        errors = verify_checksums(cf, root)
        assert errors == []

    def test_tampered_file_fails(self, tmp_path: Path) -> None:
        root = _populate(tmp_path)
        checksums = generate_checksums(root)
        cf = root / CHECKSUMS_FILENAME
        write_checksums_file(checksums, cf)

        # Tamper with a file
        (root / "a.txt").write_text("TAMPERED", encoding="utf-8")

        errors = verify_checksums(cf, root)
        assert len(errors) == 1
        assert errors[0].severity == "fatal"
        assert "a.txt" in errors[0].message

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        root = _populate(tmp_path)
        checksums = generate_checksums(root)
        cf = root / CHECKSUMS_FILENAME
        write_checksums_file(checksums, cf)

        # Remove a file
        (root / "a.txt").unlink()

        errors = verify_checksums(cf, root)
        assert len(errors) == 1
        assert "missing" in errors[0].message.lower()
