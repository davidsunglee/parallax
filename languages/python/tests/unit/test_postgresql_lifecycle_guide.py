"""The PostgreSQL lifecycle guide's code is the code that runs (no-drift guard).

Operational guidance is where a stale snippet does the most damage: it is copied
into a deployment rather than read, and nothing compiles it. So every Python
block in `docs/postgresql-lifecycle.md` that shows an application composing or
serving through a handle is written out of
`parallax.conformance.database_pooling_stories`, and this is what keeps the two
identical — byte for byte, not merely equivalent.

What executes those same functions against a real server is
`tests/api/test_database_pooling.py`. Between them, a block in the guide is
source that both compiles and passes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from parallax.conformance import database_pooling_stories

_GUIDE = Path(__file__).resolve().parents[2] / "docs" / "postgresql-lifecycle.md"

_STORY_BLOCK = re.compile(
    r"<!-- story: (?P<marker>\w+) -->\n\n```python\n(?P<body>.*?)\n```\n",
    re.DOTALL,
)

_SNIPPETS = {
    "retention_snippet": database_pooling_stories.retention_snippet,
    "observation_snippet": database_pooling_stories.observation_snippet,
    "serving_snippet": database_pooling_stories.serving_snippet,
}


def _blocks() -> dict[str, str]:
    return {
        match.group("marker"): match.group("body")
        for match in _STORY_BLOCK.finditer(_GUIDE.read_text())
    }


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


def test_the_guide_names_the_two_reporting_paths_it_does_not_control() -> None:
    # The disclosure section is the one part of this guide whose claims are
    # about what Parallax will NOT do, so the two loggers it disclaims have to
    # be named in it rather than left to a reader to infer.
    guide = _GUIDE.read_text()

    assert "parallax.resources" in guide
    assert "psycopg.pool" in guide
