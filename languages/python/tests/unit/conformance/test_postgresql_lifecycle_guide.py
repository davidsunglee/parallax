"""The PostgreSQL lifecycle guide's code is the code that runs (no-drift guard).

Operational guidance is where a stale snippet does the most damage: it is copied
into a deployment rather than read, and nothing compiles it. So every Python
block in `docs/postgresql-lifecycle.md` that shows an application composing or
serving through a handle is written out of
`parallax.conformance.database_pooling_stories`, and this is what keeps the two
identical — byte for byte, not merely equivalent.

Every block the stories do not own is held to being import lines whose names
resolve, so no block in the guide is beyond a check of some kind.

What executes those same functions against a real server is
`tests/api/test_database_pooling.py`. Between them, a block in the guide is
source that both compiles and passes.
"""

from __future__ import annotations

import ast
import importlib
import re

import pytest

from parallax.conformance import database_pooling_stories
from tests._support.repo import PY_ROOT

_GUIDE = PY_ROOT / "docs" / "postgresql-lifecycle.md"

_STORY_BLOCK = re.compile(
    r"<!-- story: (?P<marker>\w+) -->\n\n```python\n(?P<body>.*?)\n```\n",
    re.DOTALL,
)

_PYTHON_BLOCK = re.compile(r"```python\n(?P<body>.*?)\n```\n", re.DOTALL)

_SNIPPETS = {
    "construction_snippet": database_pooling_stories.construction_snippet,
    "closing_snippet": database_pooling_stories.closing_snippet,
    "retention_snippet": database_pooling_stories.retention_snippet,
    "observation_snippet": database_pooling_stories.observation_snippet,
    "serving_snippet": database_pooling_stories.serving_snippet,
}


def _blocks() -> dict[str, str]:
    return {
        match.group("marker"): match.group("body")
        for match in _STORY_BLOCK.finditer(_GUIDE.read_text())
    }


def _unmarked_bodies() -> list[str]:
    text = _GUIDE.read_text()
    owned = set(_blocks().values())
    return [
        match.group("body")
        for match in _PYTHON_BLOCK.finditer(text)
        if match.group("body") not in owned
    ]


def test_the_guide_marks_a_block_for_every_story_and_no_others() -> None:
    # A marker naming no story, or a story no block renders, is drift of its own:
    # the first would silently check nothing and the second would leave a
    # documented spelling ungraded.
    assert set(_blocks()) == set(_SNIPPETS)


@pytest.mark.parametrize("marker", sorted(_SNIPPETS))
def test_each_marked_block_is_the_story_s_own_source(marker: str) -> None:
    assert _blocks()[marker] == _SNIPPETS[marker](), (
        f"the guide's `{marker}` block is not that story's current source; replace the "
        f"block body with `{marker}()`"
    )


def test_every_block_no_story_owns_is_import_lines_whose_names_resolve() -> None:
    # The byte-exact guard above can only see a block a story renders, so the
    # rest of the guide is held to the one shape a reader can check another way:
    # imports, each name looked up on the module the guide names it from.
    bodies = _unmarked_bodies()
    assert bodies
    for body in bodies:
        for node in ast.parse(body).body:
            assert isinstance(node, ast.ImportFrom), body
            assert node.module is not None
            module = importlib.import_module(node.module)
            for alias in node.names:
                assert hasattr(module, alias.name), f"{node.module}.{alias.name}"


def test_the_guide_names_the_two_reporting_paths_it_does_not_control() -> None:
    # The disclosure section is the one part of this guide whose claims are
    # about what Parallax will NOT do, so the two loggers it disclaims have to
    # be named in it rather than left to a reader to infer.
    guide = _GUIDE.read_text()

    assert "parallax.resources" in guide
    assert "psycopg.pool" in guide
