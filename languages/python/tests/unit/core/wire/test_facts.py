"""How a scalar renders as Wire, decided once per member."""

from __future__ import annotations

import pytest

from parallax.core.base import (
    BOOLEAN,
    BYTES,
    DATE,
    FLOAT64,
    INT32,
    INT64,
    JSON,
    STRING,
    TIMESTAMP,
    NeutralType,
)
from parallax.core.wire._facts import ENCODE, ENCODE_MANY, PASS, PASS_MANY, scalar_encoding


@pytest.mark.parametrize("neutral_type", [BOOLEAN, INT32, INT64, STRING])
def test_a_type_the_codec_spells_as_its_managed_value_passes_through(
    neutral_type: NeutralType,
) -> None:
    assert scalar_encoding(neutral_type, many=False) == PASS
    assert scalar_encoding(neutral_type, many=True) == PASS_MANY


@pytest.mark.parametrize("neutral_type", [FLOAT64, BYTES, DATE, TIMESTAMP, JSON])
def test_every_other_type_is_spelled_through_the_encoder(neutral_type: NeutralType) -> None:
    assert scalar_encoding(neutral_type, many=False) == ENCODE
    assert scalar_encoding(neutral_type, many=True) == ENCODE_MANY
