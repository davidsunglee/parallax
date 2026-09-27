from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import cast

from parallax.conformance import case_format
from parallax.conformance._case_literal import normalize_case_literal
from parallax.core.base import BOOLEAN, FLOAT32, FLOAT64, INT64, STRING, TIMESTAMP


def test_a_case_literal_encodes_only_a_managed_value_without_a_json_scalar_carrier() -> None:
    authored = cast(
        "Mapping[str, object]",
        case_format.safe_load_yaml(
            "{ underflow64: -1e-400, zero64: -0.0, zero32: -0.0,"
            " text: plain, count: 3, flag: true }"
        ),
    )
    declared = {
        "underflow64": FLOAT64,
        "zero64": FLOAT64,
        "zero32": FLOAT32,
        "text": STRING,
        "count": INT64,
        "flag": BOOLEAN,
    }

    passed = {
        name: normalize_case_literal(declared[name], value) for name, value in authored.items()
    }

    assert all(passed[name] is value for name, value in authored.items()), passed
    offset = dt.datetime(2024, 3, 1, 12, 30, tzinfo=dt.timezone(dt.timedelta(hours=5)))
    assert normalize_case_literal(TIMESTAMP, offset) == "2024-03-01T07:30:00.000000Z"
