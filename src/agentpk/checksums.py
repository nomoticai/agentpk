"""SHA-256 checksum generation and verification."""

from __future__ import annotations

import hashlib
from pathlib import Path

from agentpk.constants import CHECKSUMS_FILENAME
from agentpk.exceptions import ValidationError


def compute_file_hash(file_path: Path) -> str:
    """Return ``"sha256:"`` + SHA-256 hex digest of *file_path* contents."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def compute_files_hash(file_paths: list[Path], base_dir: Path) -> str:
    """Compute a single hash over all *file_paths* combined.

    Paths are sorted by their path relative to *base_dir* before hashing
    so that the result is deterministic regardless of iteration order.

    Returns ``"sha256:"`` + hex digest.
    """
    h = hashlib.sha256()
    sorted_paths = sorted(file_paths, key=lambda p: p.relative_to(base_dir).as_posix())
    for p in sorted_paths:
        # Hash the relative path and file bytes together
        rel = p.relative_to(base_dir).as_posix()
        h.update(rel.encode("utf-8"))
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def generate_checksums(
    source_dir: Path,
    exclude: list[str] | None = None,
) -> dict[str, str]:
    """Walk *source_dir* and compute SHA-256 for every file not in *exclude*.

    Returns a dict mapping POSIX-style relative path strings to
    ``"sha256:<hex>"`` digests.  The default *exclude* list contains only
    :data:`~agentpk.constants.CHECKSUMS_FILENAME`.
    """
    if exclude is None:
        exclude = [CHECKSUMS_FILENAME]

    checksums: dict[str, str] = {}
    for file_path in sorted(source_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(source_dir).as_posix()
        if rel in exclude:
            continue
        checksums[rel] = compute_file_hash(file_path)
    return checksums


def write_checksums_file(checksums: dict[str, str], output_path: Path) -> None:
    """Write *checksums* in standard ``sha256sum`` format.

    Each line is ``"<hash>  <relative/path>\\n"``, sorted by path.
    """
    lines: list[str] = []
    for rel_path in sorted(checksums):
        digest = checksums[rel_path]
        # Strip the "sha256:" prefix for the on-disk format
        hex_only = digest.removeprefix("sha256:")
        lines.append(f"{hex_only}  {rel_path}\n")
    output_path.write_text("".join(lines), encoding="utf-8")


def read_checksums_file(checksums_path: Path) -> dict[str, str]:
    """Parse a ``checksums.sha256`` file.

    Returns a dict mapping relative path strings to ``"sha256:<hex>"``
    digests.
    """
    checksums: dict[str, str] = {}
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: "<hex>  <path>" (two-space separator, sha256sum convention)
        hex_digest, _, rel_path = line.partition("  ")
        checksums[rel_path] = f"sha256:{hex_digest}"
    return checksums


def verify_checksums(
    checksums_path: Path,
    base_dir: Path,
) -> list[ValidationError]:
    """Compare actual file hashes against a ``checksums.sha256`` file.

    Returns a list of :class:`~agentpk.exceptions.ValidationError`
    (fatal severity) for any mismatch or missing file.  Returns an empty
    list when every file passes.
    """
    errors: list[ValidationError] = []
    expected = read_checksums_file(checksums_path)

    for rel_path, expected_hash in sorted(expected.items()):
        file_path = base_dir / rel_path
        if not file_path.exists():
            errors.append(
                ValidationError(
                    f"File listed in checksums is missing: {rel_path}",
                    field=f"checksums.{rel_path}",
                    severity="fatal",
                )
            )
            continue

        actual_hash = compute_file_hash(file_path)
        if actual_hash != expected_hash:
            errors.append(
                ValidationError(
                    f"Checksum mismatch for {rel_path}: "
                    f"expected {expected_hash}, got {actual_hash}",
                    field=f"checksums.{rel_path}",
                    severity="fatal",
                )
            )

    return errors
