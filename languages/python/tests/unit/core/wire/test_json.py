from __future__ import annotations

import copy
import decimal
import json
import math
import sys
import weakref
from collections.abc import Callable
from typing import cast

import pytest

from parallax.core.base import FrozenMap, retain_document_value
from parallax.core.base._neutral import host_float_number
from parallax.core.wire._json import (
    _MAX_UNAMBIGUOUS_TOKEN_LENGTH,  # pyright: ignore[reportPrivateUsage]
    authored_number,
    authored_token,
    dump_document,
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
    assert host_float_number(value) == decimal.Decimal.from_float(value) == decimal.Decimal(token)


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
    assert (host_float_number(float(value)) != decimal.Decimal(token)) is kept


@pytest.mark.parametrize("token", ["0.1", "0.10000000000000001", "-1e-400", "1e309", "-0"])
def test_an_authored_number_is_its_own_copy_and_keeps_its_token(token: str) -> None:
    value = authored_number(token)
    assert authored_token(value) == token
    assert copy.copy(value) is value
    assert copy.deepcopy(value) is value


@pytest.mark.parametrize("token", ["0.1", "0.10000000000000001", "1e309"])
def test_an_authored_float_keeps_its_token_without_an_instance_dictionary(token: str) -> None:
    assert not hasattr(authored_number(token), "__dict__")


def _meaning(text: str) -> object:
    return json.loads(text, parse_float=decimal.Decimal, parse_int=decimal.Decimal)


def _plain(value: object) -> object:
    if isinstance(value, FrozenMap | dict):
        members = cast("dict[str, object]", value)
        return {key: _plain(member) for key, member in members.items()}
    if isinstance(value, tuple | list):
        return [_plain(member) for member in cast("list[object]", value)]
    return value


@pytest.mark.parametrize(
    "token",
    [
        "0.10000000000000001",
        "3.14159265358979323846264338327950288",
        "1.000000059604644775390625",
        "1e999",
        "-1e-400",
        "4e-324",
        "1" + "0" * 5000,
    ],
)
def test_a_retained_number_the_host_would_respell_keeps_its_exact_meaning(token: str) -> None:
    exact = decimal.Decimal(token)
    assert _meaning(dump_document(loads(token))) == exact
    assert _meaning(dump_document(loads(f"[{token}]"))) == [exact]
    retained = retain_document_value(loads(f'{{"n": [[{token}]]}}'))
    assert _meaning(dump_document(retained)) == {"n": [[exact]]}


@pytest.mark.parametrize(
    ("source", "written"),
    [
        ("[0.1, 12.50, 1e-07, 0.0000001]", "[0.1, 12.5, 1e-07, 1e-07]"),
        (
            "[0.30000000000000004, 0.000012345678901234568]",
            "[0.30000000000000004, 1.2345678901234568e-05]",
        ),
        ("[5e-324, -0, 1E2, 1, 1.0]", "[5e-324, 0, 100.0, 1, 1.0]"),
    ],
)
def test_a_retained_number_the_host_spells_with_its_meaning_keeps_the_host_spelling(
    source: str, written: str
) -> None:
    assert dump_document(retain_document_value(loads(source))) == written
    assert _meaning(written) == _meaning(source)


def test_a_respelled_document_writes_every_other_value_as_the_standard_encoder_does() -> None:
    ordinary: dict[str, object] = {
        "text": 'Bergen \u00e6 "q"',
        "count": 7,
        "ratio": 0.5,
        "retained": loads("12.34"),
        "computed": loads("0.30000000000000004"),
        "negativeZero": loads("-0"),
        "flag": True,
        "off": False,
        "none": None,
        "nested": {"list": [1, (2.5, "x")], "frozen": FrozenMap({"inner": [None]})},
    }
    respelled = loads("0.10000000000000001")
    expected = json.dumps({**cast("dict[str, object]", _plain(ordinary)), "exact": "@"})
    expected = expected.replace('"@"', "0.10000000000000001")
    assert dump_document(retain_document_value({**ordinary, "exact": respelled})) == expected
    assert dump_document({**ordinary, "exact": respelled}) == expected
    assert dump_document(FrozenMap(ordinary)) == json.dumps(_plain(ordinary))


def test_a_non_finite_float_beside_a_respelled_number_is_spelled_as_json_dumps_does() -> None:
    respelled = loads("0.10000000000000001")
    assert dump_document([respelled, math.nan, math.inf]) == "[0.10000000000000001, NaN, Infinity]"
    assert json.dumps([0.1, math.nan, math.inf]) == "[0.1, NaN, Infinity]"


@pytest.mark.parametrize("respelled", [False, True])
def test_an_unsupported_value_fails_as_the_standard_encoder_does(respelled: bool) -> None:
    members: dict[str, object] = {"unsupported": object()}
    if respelled:
        members["exact"] = loads("0.10000000000000001")
    for document in (FrozenMap(members), members):
        with pytest.raises(TypeError, match="Object of type object is not JSON serializable"):
            dump_document(document)


def test_a_yaml_number_token_is_written_as_json() -> None:
    assert _meaning(dump_document([authored_number("+1e999")])) == [decimal.Decimal("1e999")]
    assert dump_document([authored_number("+0.1")]) == "[0.1]"


def _in_array(inner: object) -> object:
    return [inner]


def _in_object(inner: object) -> object:
    return {"n": inner}


def _in_retained_object(inner: object) -> object:
    return FrozenMap({"n": (inner,)})


@pytest.mark.parametrize(
    ("enclose", "opening", "closing"),
    [
        (_in_array, "[", "]"),
        (_in_object, '{"n": ', "}"),
        (_in_retained_object, '{"n": [', "]}"),
    ],
    ids=["array", "object", "retained"],
)
@pytest.mark.parametrize("token", ["0.1", "0.10000000000000001"])
def test_a_document_nested_past_the_interpreter_recursion_limit_is_written(
    enclose: Callable[[object], object], opening: str, closing: str, token: str
) -> None:
    depth = sys.getrecursionlimit()
    document = loads(token)
    for _ in range(depth):
        document = enclose(document)
    assert dump_document(document) == opening * depth + token + closing * depth


def _self_containing(member: object) -> list[object]:
    document: list[object] = [member]
    document.append(document)
    return document


@pytest.mark.parametrize(
    "document",
    [
        _self_containing(loads("0.1")),
        _self_containing(loads("0.10000000000000001")),
        _self_containing(FrozenMap({"exact": loads("0.10000000000000001")})),
    ],
)
def test_a_circular_document_fails_as_the_standard_encoder_does(document: object) -> None:
    with pytest.raises(ValueError, match="Circular reference detected"):
        dump_document(document)
