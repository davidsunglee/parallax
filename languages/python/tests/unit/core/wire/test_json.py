from __future__ import annotations

import decimal
import json
import weakref
from typing import cast

import pytest

from parallax.core.base import FLOAT32, FLOAT64, INT64
from parallax.core.base._neutral import host_float_number
from parallax.core.wire._json import (
    _MAX_UNAMBIGUOUS_TOKEN_LENGTH,  # pyright: ignore[reportPrivateUsage]
    authored_token,
    loads,
    prepared_loads,
)


class _NameCache(dict[str, str]):
    pass


def test_released_prepared_loader_frees_its_state_without_cycle_collection() -> None:
    cache = _NameCache()
    released = weakref.ref(cache)
    loader = prepared_loads(name_cache=cache)
    assert loader('{"name": 1}') == {"name": 1}

    del cache, loader

    assert released() is None


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ('{"x": 1, "x": 2}', "duplicate object member name 'x'"),
        ('{"x": NaN}', "invalid JSON numeric constant 'NaN'"),
    ],
)
def test_reused_prepared_loader_reports_the_current_source(source: str, message: str) -> None:
    loader = prepared_loads()
    assert loader(b'{"previous": 1}') == {"previous": 1}

    with pytest.raises(json.JSONDecodeError) as caught:
        loader(source.encode())

    assert caught.value.msg == message
    assert caught.value.doc == source
    assert caught.value.pos == 0
    assert loader('{"next": 2}') == {"next": 2}


@pytest.mark.parametrize(
    "token", ["54102915422.9375", "-5410291542.9375", "99867008926416.0", "1.52587890625e-5"]
)
def test_an_exact_token_at_the_length_bound_leaves_a_float_every_member_reads_it_from(
    token: str,
) -> None:
    assert len(token) == _MAX_UNAMBIGUOUS_TOKEN_LENGTH
    value = loads(token)
    assert type(value) is float
    for member in (FLOAT32, FLOAT64, INT64):
        assert host_float_number(value, member) == decimal.Decimal(token)


@pytest.mark.parametrize(
    ("token", "kept"),
    [
        ("0.000030517578125", False),
        ("562949953421312.25", True),
        ("1.000000059604644775390625", True),
    ],
)
def test_an_exact_token_past_the_length_bound_keeps_its_digits_only_for_another_float32_number(
    token: str, kept: bool
) -> None:
    assert len(token) > _MAX_UNAMBIGUOUS_TOKEN_LENGTH
    value = cast("float", loads(token))
    assert (authored_token(value) == token) is kept
    assert (host_float_number(float(value), FLOAT32) != decimal.Decimal(token)) is kept
