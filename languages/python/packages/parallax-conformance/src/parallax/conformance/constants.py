"""Pinned provisioning constants (spec §6).

The single module that pins the self-managed Testcontainers Postgres image to an
exact version **and** sha256 digest. Bumps are reviewed diffs: change the tag and
the digest together here, nowhere else.
"""

from __future__ import annotations

from typing import Final

__all__ = ["POSTGRES_DIGEST", "POSTGRES_IMAGE", "POSTGRES_TAG"]

POSTGRES_TAG: Final[str] = "postgres:16.4-alpine"
POSTGRES_DIGEST: Final[str] = (
    "sha256:5660c2cbfea50c7a9127d17dc4e48543eedd3d7a41a595a2dfa572471e37e64c"
)

# The exact image reference (tag pinned to its content digest) the provisioner
# boots. Digest-pinning makes the base image reproducible; the human-readable tag
# rides alongside for review.
POSTGRES_IMAGE: Final[str] = f"postgres:16.4-alpine@{POSTGRES_DIGEST}"
