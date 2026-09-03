"""Pinned provisioning constants (spec §6).

The single module that pins the self-managed Testcontainers Postgres image to an
exact version **and** sha256 digest. Bumps are reviewed diffs: change the tag and
the digest together here, nowhere else.
"""

from __future__ import annotations

from typing import Final

__all__ = ["POSTGRES_DIGEST", "POSTGRES_IMAGE", "POSTGRES_TAG"]

POSTGRES_TAG: Final[str] = "postgres:18.6-alpine"
POSTGRES_DIGEST: Final[str] = (
    "sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2"
)

# The exact image reference (tag pinned to its content digest) the provisioner
# boots. Digest-pinning makes the base image reproducible; the human-readable tag
# rides alongside for inspection.
POSTGRES_IMAGE: Final[str] = f"{POSTGRES_TAG}@{POSTGRES_DIGEST}"
