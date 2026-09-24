from __future__ import annotations

import pytest

from parallax.conformance._mechanism.dialects import DIALECT_CATALOG, dialect_for
from parallax.core.dialect import POSTGRES


def test_a_shipped_dialect_resolves_to_its_strategy() -> None:
    assert dialect_for("postgres") is POSTGRES


def test_the_supported_dialect_catalog_is_the_specification_s() -> None:
    # The catalog names every Dialect the specification supports, whether or not
    # this implementation ships a strategy for it, so a consumer enumerating it
    # reports the gap rather than narrowing the matrix to what it happens to have.
    assert DIALECT_CATALOG == ("postgres", "mariadb")
    with pytest.raises(ValueError, match="unsupported dialect"):
        dialect_for("mariadb")
