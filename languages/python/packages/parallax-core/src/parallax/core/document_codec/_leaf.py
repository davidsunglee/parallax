"""The portable leaf encoding table (m-document-codec, "Portable leaf encodings").

One function answers "how is this leaf spelled inside a document", for both document
kinds and at every depth. Decoding is its inverse and is not restated here: the
portable literal inverse is :func:`~parallax.core.base.decode_neutral_literal`, which
the float rule below also measures its own round trip through, so the two legs cannot
drift.

The string spellings are comparison-significant, not house style. SQL compares the six
text-compared types by comparing the extracted text directly, so changing one changes
predicate and ordering results and MUST move `m-dialect`'s corresponding decision with
it rather than travel alone.
"""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import uuid as _uuid
from typing import cast

from parallax.core.base import (
    Boolean,
    Bytes,
    Date,
    Decimal,
    Float32,
    Float64,
    Int32,
    Int64,
    Json,
    NeutralType,
    String,
    Time,
    Timestamp,
    Uuid,
    decode_neutral_literal,
    matches_neutral_type,
)

__all__ = ["LeafEncodingError", "encode_leaf", "is_text_compared"]

# The declared types whose document form is a JSON string AND whose SQL comparison is
# of the extracted text rather than of a cast (`m-dialect`). `decimal(p, s)` is a JSON
# string too and is deliberately absent: it casts with the numeric family, because its
# integer part has no fixed width, so `10.00` sorts below `9.00` as text.
_TEXT_COMPARED: tuple[type, ...] = (String, Bytes, Date, Time, Timestamp, Uuid)

# The widest decimal rendering `%.{p}g` can need to round-trip a binary64, and so the
# upper bound of the shortest-number search below.
_MAX_SIGNIFICANT_DIGITS = 17


class LeafEncodingError(Exception):
    """A value is not a member of the Neutral Type its leaf declares.

    Raised rather than encoded. The table is total over the type algebra but says
    nothing about a value outside a declared value space, and inventing a spelling for
    one is exactly what this module exists to prevent.
    """


def is_text_compared(neutral_type: NeutralType) -> bool:
    """Whether a document-resident member of ``neutral_type`` compares as extracted
    text rather than through a dialect cast (`m-dialect`)."""
    return isinstance(neutral_type, _TEXT_COMPARED)


def encode_leaf(neutral_type: NeutralType, value: object) -> object:
    """``value``'s one document spelling under ``neutral_type``.

    Every Neutral Type has exactly one, so two writers of one value produce one
    document. The result is a portable JSON value — never a driver value, a rendered
    text, or a provider-native document handle.
    """
    if not matches_neutral_type(value, neutral_type):
        raise LeafEncodingError(
            f"{value!r} is not a member of the declared value space {neutral_type!r}"
        )
    match neutral_type:
        case Boolean() | Int32() | Int64() | String() | Json():
            return value
        case Float32() | Float64():
            return _shortest_float(cast("float", value), neutral_type)
        case Decimal(_precision, scale):
            return _exact_decimal(cast("_decimal.Decimal", value), scale)
        case Bytes():
            return cast("bytes", value).hex()
        case Date():
            return cast("_dt.date", value).isoformat()
        case Time():
            return cast("_dt.time", value).isoformat()
        case Timestamp():
            dt = cast("_dt.datetime", value).astimezone(_dt.UTC)
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        case Uuid():
            return str(cast("_uuid.UUID", value))


def _exact_decimal(value: _decimal.Decimal, scale: int) -> str:
    """The exact decimal spelling: a ``-`` only for a value below zero, the integer
    digits with no leading zero (a single ``0`` when the integer part is zero), and —
    when ``scale > 0`` — ``.`` and exactly ``scale`` fraction digits.

    Rescaling is exact by construction rather than by a rounding context: membership
    already established the value needs no more fraction digits than ``scale`` admits,
    so the shift below only ever pads with zeros, at any precision.
    """
    sign, digits, exponent = value.as_tuple()
    unscaled = 0
    for digit in digits:
        unscaled = unscaled * 10 + digit
    unscaled *= 10 ** (cast("int", exponent) + scale)
    padded = str(unscaled).rjust(scale + 1, "0")
    body = f"{padded[:-scale]}.{padded[-scale:]}" if scale else padded
    return f"-{body}" if sign and unscaled else body


def _shortest_float(value: float, neutral_type: Float32 | Float64) -> float:
    """The number with the fewest significant digits that decodes back to ``value``
    under the declared width, nearest among equally short ones, and — where two are
    equally near — the one whose last significant digit is even.

    All three levels are load-bearing: binary64 ``562949953421312.25`` is decoded from
    both ``562949953421312.2`` and ``562949953421312.3``, so the first two alone still
    admit two numbers. ``%.{p}g`` supplies all three at once, because it renders the
    correctly-rounded ``p``-digit decimal and breaks its own tie to even.

    "Decodes back to" is measured through the decode leg itself, so the phrase cannot
    mean one thing while encoding and another while reading: a ``float32``'s decode
    reads a number at binary32, which is why ``1048576.2`` is admissible for
    ``1048576.25`` at that width and for nothing at binary64.

    The answer is the float, not its rendering: ``20`` and ``20.0`` are one JSON
    number, while ``0.1`` and ``0.10000000000000001`` are two and only the first is
    admissible.
    """
    target = cast("float", decode_neutral_literal(value, neutral_type))
    for precision in range(1, _MAX_SIGNIFICANT_DIGITS + 1):
        candidate = float(f"{target:.{precision}g}")
        if decode_neutral_literal(candidate, neutral_type) == target:
            return candidate
    return target  # pragma: no cover - 17 significant digits always round-trip
