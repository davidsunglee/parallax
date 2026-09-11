"""The test-authored Wire spelling of a managed value, for suites that state a
statement's sparse Wire overrides or a find step's own rows by hand.

A sparse override rather than production type inference: it spells what a
test authored, so a value the compiler would project differently is a
difference the test sees. Exported names carry no leading underscore:
importing an underscored name across modules is a ``reportPrivateUsage``
error under pyright strict, so privacy is carried by this MODULE's
underscore. Never imported by production code.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Mapping, Sequence
from typing import cast

from parallax.core.base import TemporalBound

__all__ = ["wire_value"]


def wire_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        source = cast("Mapping[object, object]", value)
        return {str(name): wire_value(item) for name, item in source.items()}
    if isinstance(value, (list, tuple)):
        source = cast("Sequence[object]", value)
        return [wire_value(item) for item in source]
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.UTC).isoformat()
    if isinstance(value, dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return "infinity" if isinstance(value, TemporalBound) else value
