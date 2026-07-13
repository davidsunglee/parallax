"""Postgres adapter internal-seam unit tests (Docker-free).

The public export is ``PostgresAdapter`` alone (§8 topology); psycopg bind
mechanics stay internal. The bind-adaptation seam — the neutral ``JsonDocument``
carrier becoming a psycopg ``Jsonb`` at the adapter boundary — is pure and proven
here without a container.
"""

from __future__ import annotations

import pytest
from psycopg.types.json import Jsonb

import parallax.postgres
from parallax.core.db_port import JsonDocument
from parallax.postgres.adapter import adapt_binds

pytestmark = pytest.mark.unit


def test_public_surface_is_the_adapter_alone() -> None:
    assert parallax.postgres.__all__ == ["PostgresAdapter"]
    assert not hasattr(parallax.postgres, "Json")
    assert not hasattr(parallax.postgres, "Jsonb")


def testadapt_binds_wraps_json_documents_and_passes_scalars_through() -> None:
    adapted = adapt_binds([1, "x", JsonDocument({"city": "Oslo"}), None])
    assert adapted[0] == 1
    assert adapted[1] == "x"
    assert isinstance(adapted[2], Jsonb)
    assert adapted[3] is None


def testadapt_binds_wraps_the_document_value() -> None:
    document = {"geo": {"lat": 1}}
    (adapted,) = adapt_binds([JsonDocument(document)])
    assert isinstance(adapted, Jsonb)
    assert adapted.obj == document
