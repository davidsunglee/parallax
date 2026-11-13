"""The Database Bindings conformance runs and stories place their models under."""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from typing import Final, cast

from parallax.conformance import case_format
from parallax.postgres import PostgresBinding, PostgresLocation

__all__ = [
    "DEFAULT_BINDING",
    "DEFAULT_QUALIFIER",
    "binding_document",
    "corpus_default_document",
]

DEFAULT_QUALIFIER: Final = "px"
"""The schema the corpus default binding places every table and sequence in."""

DEFAULT_BINDING: Final = PostgresBinding(default=PostgresLocation(schema=DEFAULT_QUALIFIER))
"""The PostgreSQL corpus default binding, as stories and tests spell it in code."""


@cache
def _default_documents() -> Mapping[str, Mapping[str, object]]:
    path = case_format.find_repo_root() / "core" / "compatibility" / "bindings" / "default.yaml"
    loaded = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):  # pragma: no cover - the corpus default is a mapping
        raise ValueError(f"{path}: the corpus default binding is a dialect-keyed mapping")
    return cast("Mapping[str, Mapping[str, object]]", loaded)


def corpus_default_document(dialect: str) -> Mapping[str, object]:
    """The corpus default binding document for ``dialect``."""
    return _default_documents()[dialect]


def binding_document(
    bindings: object, dialect: str, *, inherited: object = None
) -> Mapping[str, object]:
    """The binding document a dialect-keyed case ``bindings`` map names for
    ``dialect``, else the one ``inherited`` names, else the corpus default.
    """
    for candidate in (bindings, inherited):
        if isinstance(candidate, Mapping):
            document = cast("Mapping[str, object]", candidate).get(dialect)
            if document is not None:
                if not isinstance(document, Mapping):
                    raise ValueError(f"a {dialect} binding is a binding document, not {document!r}")
                return cast("Mapping[str, object]", document)
    return corpus_default_document(dialect)
