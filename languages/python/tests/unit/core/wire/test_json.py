from __future__ import annotations

import json
import weakref

import pytest

from parallax.core.wire._json import prepared_loads


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
