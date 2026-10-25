"""Each guide chapter's imports block names every public name its snippets use."""

from __future__ import annotations

import ast
import builtins
import re

import pytest

from parallax.conformance import case_format, guide_models
from parallax.conformance.usage_guide import snippet_sources

_GUIDE = case_format.find_repo_root() / "languages" / "python" / "docs" / "guide"
_MARKER = re.compile(r"<!-- example: ([a-z0-9][a-z0-9-]*) -->")
_EXAMPLE_BLOCK = re.compile(r"<!-- example: .*?<!-- /example -->", re.DOTALL)
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_SHOP_MODEL_NAMES: frozenset[str] = frozenset(guide_models.__all__) - {"SHOP_MODEL"}
_NOTHING_ASSUMED: frozenset[str] = frozenset()


def _bound_and_loaded(source: str) -> tuple[set[str], set[str]]:
    """Every name ``source`` binds and every name it reads, scope-blind."""
    bound: set[str] = set()
    loaded: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.alias):
            bound.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.FunctionDef | ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            bound.add(node.name)
        elif isinstance(node, ast.Name):
            (bound if isinstance(node.ctx, ast.Store) else loaded).add(node.id)
    return bound, loaded


@pytest.mark.parametrize(
    ("chapter", "imports_id", "assumed"),
    [
        pytest.param("01-getting-started.md", "getting-started-imports", _NOTHING_ASSUMED, id="01"),
        pytest.param("02-modeling.md", "modeling-imports", _NOTHING_ASSUMED, id="02"),
        pytest.param("03-reading.md", "reading-imports", _SHOP_MODEL_NAMES, id="03"),
        pytest.param("04-writing.md", "writing-imports", _SHOP_MODEL_NAMES, id="04"),
        pytest.param("05-transactions.md", "transactions-imports", _SHOP_MODEL_NAMES, id="05"),
        pytest.param(
            "06-execution-authority.md", "execution-authority-imports", _SHOP_MODEL_NAMES, id="06"
        ),
        pytest.param(
            "07-model-evolution.md", "model-evolution-imports", _SHOP_MODEL_NAMES, id="07"
        ),
        pytest.param("08-errors.md", "errors-imports", _SHOP_MODEL_NAMES, id="08"),
        pytest.param("09-operations.md", "operations-imports", _SHOP_MODEL_NAMES, id="09"),
    ],
)
def test_each_chapters_imports_bind_what_its_snippets_read_and_only_what_it_names(
    chapter: str, imports_id: str, assumed: frozenset[str]
) -> None:
    # A reader finds every name a chapter uses in its imports block. The block
    # has to resolve, cover every name the chapter's snippets read beyond the
    # shop model the later chapters assume, and import nothing the chapter
    # neither reads in a snippet nor names in its prose.
    text = (_GUIDE / chapter).read_text(encoding="utf-8")
    sources = snippet_sources()
    marked = _MARKER.findall(text)
    assert imports_id in marked
    imports = sources[imports_id]
    exec(compile(imports, imports_id, "exec"), {})
    bound, loaded = _bound_and_loaded("\n\n".join(sources[source_id] for source_id in marked))
    imported, _ = _bound_and_loaded(imports)
    named = {
        name
        for span in _CODE_SPAN.findall(_EXAMPLE_BLOCK.sub("", text))
        for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", span)
    }

    assert loaded - bound - set(dir(builtins)) - assumed == set()
    assert imported - loaded - named == set()
