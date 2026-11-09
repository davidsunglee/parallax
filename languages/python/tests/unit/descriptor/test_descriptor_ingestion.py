"""The canonical metamodel schema descriptor ingestion validates against."""

from __future__ import annotations

from parallax.descriptor import _ingest
from tests._support.repo import REPO_ROOT


def test_the_schema_phase_validates_against_the_packaged_authoritative_schema() -> None:
    # The distribution embeds its own copy and reads it through
    # `importlib.resources`, never a repository-relative path — so the check that
    # matters is that the packaged bytes ARE the authoritative bytes. The artifact
    # lane proves the same for the built wheel; this proves it for the source tree
    # the descriptor-error sweep validates through.
    authoritative = (REPO_ROOT / "core" / "schemas" / "metamodel.schema.json").read_text(
        encoding="utf-8"
    )
    assert _ingest.schema_text() == authoritative
    assert _ingest.SCHEMA_RESOURCE == "_schemas/metamodel.schema.json"
