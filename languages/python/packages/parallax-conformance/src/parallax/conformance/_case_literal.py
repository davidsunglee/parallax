from __future__ import annotations

import datetime as dt
from typing import cast

from parallax.core.base import TIMESTAMP, ManagedValue, NeutralType, matches_neutral_type
from parallax.core.wire import encode_wire


def normalize_case_literal(neutral_type: NeutralType, value: object | None) -> object | None:
    """Encode a synthetic managed value that has no JSON scalar carrier, such as a
    ``datetime``, as canonical Wire.

    JSON scalars, including the authored-number carriers the case loader produces,
    pass through unchanged so production Wire decoding reads the authored token.
    """
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if matches_neutral_type(value, neutral_type):
        return encode_wire(neutral_type, cast("ManagedValue", value))
    return value


def normalize_case_bound(value: str | dt.datetime | None) -> str | None:
    normalized = normalize_case_literal(TIMESTAMP, value)
    return None if normalized is None else cast("str", normalized)
