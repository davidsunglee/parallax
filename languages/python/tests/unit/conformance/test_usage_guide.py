"""Usage Guide generator: example-block expansion over the managed Markdown files."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from parallax.conformance import api_suite, usage_guide
from parallax.conformance.api_suite import Example, Recipe
from parallax.conformance.usage_guide import GuideError

_SOURCES = {"m-a-001": "first()", "a-recipe": "second()\nthird()"}


def test_expand_fills_each_block_and_preserves_the_prose_around_it() -> None:
    text = (
        "Intro.\n\n"
        "<!-- example: m-a-001 -->\nstale body\n<!-- /example -->\n\n"
        "Between.\n\n"
        "<!-- example: a-recipe -->\n<!-- /example -->\n"
        "Outro.\n"
    )

    assert usage_guide.expand(text, _SOURCES, origin="page.md") == (
        "Intro.\n\n"
        "<!-- example: m-a-001 -->\n```python\nfirst()\n```\n<!-- /example -->\n\n"
        "Between.\n\n"
        "<!-- example: a-recipe -->\n```python\nsecond()\nthird()\n```\n<!-- /example -->\n"
        "Outro.\n"
    )


def test_expand_is_a_fixed_point_and_leaves_marker_free_text_alone() -> None:
    once = usage_guide.expand(
        "<!-- example: m-a-001 -->\n<!-- /example -->\n", _SOURCES, origin="page.md"
    )

    assert usage_guide.expand(once, _SOURCES, origin="page.md") == once
    plain = "# Title\n\n<!-- a comment about examples -->\n```python\nx = 1\n```\n"
    assert usage_guide.expand(plain, _SOURCES, origin="page.md") == plain


@pytest.mark.parametrize(
    ("text", "message"),
    [
        pytest.param(
            "<!-- example: m-ghost-404 -->\n<!-- /example -->\n",
            "page.md:1: unknown snippet source ID: m-ghost-404",
            id="unknown",
        ),
        pytest.param(
            "<!-- example: m-a-001 -->\n<!-- example: a-recipe -->\n<!-- /example -->\n",
            "page.md:2: example marker nested in the block opened at line 1",
            id="nested",
        ),
        pytest.param(
            "prose\n<!-- /example -->\n",
            "page.md:2: closing example marker without an opening",
            id="unmatched",
        ),
        pytest.param(
            "<!-- example: m-a-001 -->\nbody\n",
            "page.md:1: example block is never closed",
            id="unterminated",
        ),
        pytest.param("<!-- example m-a-001 -->\n", "page.md:1: malformed", id="no-colon"),
        pytest.param("<!--example: m-a-001-->\n", "page.md:1: malformed", id="no-spacing"),
        pytest.param("  <!-- example: m-a-001 -->\n", "page.md:1: malformed", id="indented"),
        pytest.param("<!-- example: M-A-001 -->\n", "page.md:1: malformed", id="bad-id"),
        pytest.param(
            "<!-- example: m-a-001 -->\n<!-- /example --> trailing\n",
            "page.md:2: malformed",
            id="close-with-text",
        ),
    ],
)
def test_expand_refuses_invalid_markers(text: str, message: str) -> None:
    with pytest.raises(GuideError, match=re.escape(message)):
        usage_guide.expand(text, _SOURCES, origin="page.md")


def test_snippet_sources_key_examples_by_case_and_recipes_by_recipe_id() -> None:
    sources = usage_guide.snippet_sources(
        [Example("m-a-001", "t", "first()\n")], [Recipe("a-recipe", "t", "second()\n")]
    )

    assert sources == {"m-a-001": "first()", "a-recipe": "second()"}


@pytest.mark.parametrize(
    ("examples", "recipes"),
    [
        pytest.param(
            [Example("m-a-001", "t", "s"), Example("m-a-001", "u", "s")], [], id="examples"
        ),
        pytest.param([], [Recipe("a", "t", "s"), Recipe("a", "u", "s")], id="recipes"),
        pytest.param([Example("m-a-001", "t", "s")], [Recipe("m-a-001", "t", "s")], id="across"),
    ],
)
def test_snippet_sources_refuse_a_duplicate_id(
    examples: list[Example], recipes: list[Recipe]
) -> None:
    with pytest.raises(GuideError, match="duplicate snippet source ID"):
        usage_guide.snippet_sources(examples, recipes)


def test_snippet_sources_refuse_an_id_no_marker_can_name() -> None:
    with pytest.raises(GuideError, match="cannot be named by a marker"):
        usage_guide.snippet_sources([], [Recipe("Stream Results", "t", "s")])


def test_registered_examples_and_recipes_have_unique_markable_ids() -> None:
    sources = usage_guide.snippet_sources()

    assert {example.case_id for example in api_suite.EXAMPLES} <= sources.keys()
    assert {recipe.recipe_id for recipe in api_suite.RECIPES} <= sources.keys()


def _repo(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


_GUIDE = "languages/python/docs/guide"


def test_managed_files_are_the_readme_and_every_guide_page(tmp_path: Path) -> None:
    _repo(
        tmp_path,
        {
            "README.md": "",
            f"{_GUIDE}/b.md": "",
            f"{_GUIDE}/part/a.md": "",
            f"{_GUIDE}/notes.txt": "",
            "languages/python/docs/other.md": "",
        },
    )

    assert usage_guide.managed_paths(tmp_path) == [
        tmp_path / "README.md",
        tmp_path / _GUIDE / "b.md",
        tmp_path / _GUIDE / "part" / "a.md",
    ]


def test_main_rewrites_stale_blocks_and_check_then_passes(tmp_path: Path) -> None:
    marked = "Tour.\n\n<!-- example: stream-results -->\n<!-- /example -->\n"
    _repo(tmp_path, {"README.md": marked, f"{_GUIDE}/01-page.md": "# Page\n"})

    assert usage_guide.main(["--check"], root=tmp_path) == 1
    assert usage_guide.main([], root=tmp_path) == 0
    assert usage_guide.main(["--check"], root=tmp_path) == 0

    stream_results = next(r for r in api_suite.RECIPES if r.recipe_id == "stream-results")
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("Tour.\n\n<!-- example: stream-results -->\n```python\n")
    assert stream_results.snippet.rstrip("\n") in readme
    assert (tmp_path / _GUIDE / "01-page.md").read_text(encoding="utf-8") == "# Page\n"


def test_check_names_every_stale_file_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    marked = "<!-- example: stream-results -->\n<!-- /example -->\n"
    _repo(tmp_path, {"README.md": marked, f"{_GUIDE}/01-page.md": marked})

    assert usage_guide.main(["--check"], root=tmp_path) == 1

    error = capsys.readouterr().err
    assert "README.md is out of date" in error
    assert f"{_GUIDE}/01-page.md is out of date" in error
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == marked


@pytest.mark.parametrize("argv", [[], ["--check"]], ids=["write", "check"])
def test_main_reports_an_invalid_marker_and_writes_nothing(
    argv: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stale = "<!-- example: stream-results -->\n<!-- /example -->\n"
    unknown = "# Page\n\n<!-- example: m-ghost-404 -->\n<!-- /example -->\n"
    _repo(tmp_path, {"README.md": stale, f"{_GUIDE}/01-page.md": unknown})

    assert usage_guide.main(argv, root=tmp_path) == 1

    assert f"{_GUIDE}/01-page.md:3: unknown snippet source ID" in capsys.readouterr().err
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == stale
