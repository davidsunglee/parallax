"""Python-annotation to Neutral Type inference (m-core).

The Neutral Type vocabulary is ``m-core``-owned, so the mapping from a native
Python scalar carrier to its structured Neutral Type belongs here rather than in
any one frontend. The mapping is exact-type rather than subclass-based: a
``datetime`` is a ``date`` subclass but a distinct value space.

``decimal.Decimal`` is deliberately absent from the mapping. The
:class:`~parallax.core.base.Decimal` variant is parametric with no defaults, so
its precision and scale come from the declaration rather than from the
annotation, and a frontend classifies the missing parameters in its own
vocabulary.
"""

from __future__ import annotations

import datetime as _dt
import uuid as _uuid
from collections.abc import Mapping
from typing import Final

from parallax.core.base._neutral import (
    BOOLEAN,
    BYTES,
    DATE,
    FLOAT64,
    INT64,
    STRING,
    TIME,
    TIMESTAMP,
    UUID,
    NeutralType,
)

__all__ = ["NEUTRAL_FROM_PYTHON", "infer_neutral_type"]

NEUTRAL_FROM_PYTHON: Final[Mapping[type, NeutralType]] = {
    bool: BOOLEAN,
    int: INT64,
    float: FLOAT64,
    str: STRING,
    bytes: BYTES,
    _dt.date: DATE,
    _dt.time: TIME,
    _dt.datetime: TIMESTAMP,
    _uuid.UUID: UUID,
}
"""The widest Neutral Type each native scalar carrier denotes. The narrower
``Int32``/``Float32`` members of those two families are reached only through an
explicit declaration option."""


def infer_neutral_type(python_type: object) -> NeutralType | None:
    """The Neutral Type ``python_type`` denotes, or ``None`` for an unmapped type.

    Error-neutral by design: a caller classifies absence in its own vocabulary,
    and an unparameterized ``decimal.Decimal`` is absent here because its
    parameters are a declaration fact.
    """
    if isinstance(python_type, type):
        return NEUTRAL_FROM_PYTHON.get(python_type)
    return None
