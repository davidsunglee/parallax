"""The serialized spelling of the ``m-core`` Neutral Type algebra (m-descriptor).

``m-descriptor`` alone owns how a Neutral Type is written down. A spelling is a
single lowercase token, and ``decimal`` is the only parameterized one:
``decimal(<precision>,<scale>)`` with both parameters required, spelled as
unsigned canonical decimal digits, and no interior whitespace. The structured
variant a spelling denotes never crosses the ``m-metamodel`` interface as text.

Resolution is error-neutral: a spelling the algebra cannot represent resolves to
absence so the calling seam classifies it in its own vocabulary, where an
unrepresentable spelling is a value-phase rejection rather than a shape defect.
"""

from __future__ import annotations

import re
from typing import Final

from parallax.core.base import (
    BOOLEAN,
    BYTES,
    DATE,
    FLOAT32,
    FLOAT64,
    INT32,
    INT64,
    JSON,
    STRING,
    TIME,
    TIMESTAMP,
    UUID,
    Decimal,
    NeutralType,
)

__all__ = ["format_type_spelling", "parse_type_spelling"]

_NULLARY_SPELLINGS: Final[dict[str, NeutralType]] = {
    "boolean": BOOLEAN,
    "int32": INT32,
    "int64": INT64,
    "float32": FLOAT32,
    "float64": FLOAT64,
    "string": STRING,
    "bytes": BYTES,
    "date": DATE,
    "time": TIME,
    "timestamp": TIMESTAMP,
    "uuid": UUID,
    "json": JSON,
}

# The exact inverse of the nullary spelling table, so a formatted spelling always
# parses back to the value it named. Variants are frozen value objects compared by
# value, so a freshly constructed nullary type keys the same entry as its singleton.
_NULLARY_FORMATS: Final[dict[NeutralType, str]] = {
    neutral: spelling for spelling, neutral in _NULLARY_SPELLINGS.items()
}

# A canonical unsigned parameter pair: no sign, no interior space, and no
# leading zero, so one bounded Decimal has exactly one spelling.
_DECIMAL_SPELLING: Final[re.Pattern[str]] = re.compile(
    r"^decimal\((0|[1-9][0-9]*),(0|[1-9][0-9]*)\)$"
)


def parse_type_spelling(spelling: str) -> NeutralType | None:
    """The Neutral Type ``spelling`` denotes, or absence when it denotes none.

    Absence covers an unknown token, a non-canonical ``decimal`` parameter pair,
    and parameters outside the ``m-core`` bounds — all of which the canonical
    schema admits as text, so the type algebra is the only place they are
    rejected.
    """
    nullary = _NULLARY_SPELLINGS.get(spelling)
    if nullary is not None:
        return nullary
    parameters = _DECIMAL_SPELLING.match(spelling)
    if parameters is None:
        return None
    precision, scale = int(parameters.group(1)), int(parameters.group(2))
    if precision < 1 or not 0 <= scale <= precision:
        return None
    return Decimal(precision, scale)


def format_type_spelling(neutral: NeutralType) -> str:
    """The canonical spelling ``neutral`` is written as — the inverse of
    :func:`parse_type_spelling`.

    ``decimal`` is the sole parameterized spelling: its precision and scale are
    written as unsigned canonical digits with no interior whitespace, so the
    result round-trips back to the same bounded :class:`~parallax.core.base.Decimal`.
    Every other variant has a single lowercase token.
    """
    if isinstance(neutral, Decimal):
        return f"decimal({neutral.precision},{neutral.scale})"
    return _NULLARY_FORMATS[neutral]
