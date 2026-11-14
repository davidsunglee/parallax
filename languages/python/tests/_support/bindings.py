"""The production binding tests place their models under."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Final, cast

from parallax.conformance import case_format
from parallax.conformance.bindings import DEFAULT_BINDING, DEFAULT_QUALIFIER, binding_document
from parallax.core.internal.database_binding import (
    DatabaseBinding,
    PhysicalTable,
    ResolvedBinding,
    ResolvedTable,
)
from parallax.core.internal.dialect import POSTGRES, Dialect
from parallax.core.internal.metamodel import EntityIdentity, Metamodel
from parallax.core.internal.storage_layout import TableLayout
from parallax.postgres import PostgresBinding, PostgresLocation, PostgresSequence, PostgresTable

__all__ = [
    "TEST_BINDING",
    "TEST_SCHEMA",
    "binding_for",
    "bound_model",
    "corpus_binding",
    "physical_table",
    "resolved_table",
]

TEST_BINDING: Final[PostgresBinding] = DEFAULT_BINDING
"""The corpus default binding: every table and sequence in the ``px`` schema."""

TEST_SCHEMA: Final = DEFAULT_QUALIFIER
"""The schema :data:`TEST_BINDING` places everything in."""


def bound_model(model: Metamodel) -> ResolvedBinding:
    """``model`` resolved under :data:`TEST_BINDING`."""
    return ResolvedBinding(model, TEST_BINDING)


@dataclass(frozen=True, slots=True)
class _DialectBinding:
    dialect: Dialect
    default: PostgresLocation | None = field(
        default_factory=lambda: PostgresLocation(DEFAULT_QUALIFIER)
    )
    namespaces: Mapping[str, PostgresLocation] = field(default_factory=dict[str, PostgresLocation])
    entities: Mapping[EntityIdentity, PostgresTable] = field(
        default_factory=dict[EntityIdentity, PostgresTable]
    )
    sequences: Mapping[str, PostgresSequence] = field(default_factory=dict[str, PostgresSequence])


def binding_for(dialect: Dialect) -> DatabaseBinding:
    """A binding placing everything in ``px`` for a dialect no backend package
    ships, so a test of a dialect decision reaches Schema Delta or SQL generation
    through the ordinary resolved-binding seam."""
    return _DialectBinding(dialect)


def physical_table(name: str, qualifier: tuple[str, ...] = (DEFAULT_QUALIFIER,)) -> PhysicalTable:
    """The physical table ``name`` in ``qualifier``, the test schema by default."""
    return PhysicalTable(qualifier, name)


def resolved_table(
    owner: EntityIdentity,
    name: str,
    qualifier: tuple[str, ...] = (DEFAULT_QUALIFIER,),
    layout: TableLayout | None = None,
) -> ResolvedTable:
    """A hand-built resolved table for a Schema Delta definition a test states
    directly; ``layout`` is absent where nothing the test reaches reads it."""
    physical = PhysicalTable(qualifier, name)
    return ResolvedTable(
        mapping_owner=owner,
        physical=physical,
        sql=POSTGRES.render_table(physical),
        layout=cast("TableLayout", layout),
        temporal_constraints=None,
        document_root_constraint=None,
    )


@cache
def _corpus_case_bindings() -> Mapping[str, PostgresBinding]:
    cases = Path(case_format.find_repo_root()) / "core" / "compatibility" / "cases"
    held: dict[str, PostgresBinding] = {}
    for path in sorted(cases.glob("*.yaml")):
        document = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            continue
        fields = cast("Mapping[str, object]", document)
        bindings = fields.get("binding")
        when = fields.get("when")
        evolve = (
            cast("Mapping[str, object]", when).get("evolve") if isinstance(when, Mapping) else None
        )
        placed: list[tuple[object, object]] = [(fields.get("model"), bindings)]
        if isinstance(evolve, Mapping):
            endpoints = cast("Mapping[str, object]", evolve)
            placed.extend(
                (endpoints.get(side), endpoints.get(f"{side}Binding") or bindings)
                for side in ("earlier", "later")
            )
        for model, authored in placed:
            if isinstance(model, str) and authored is not None:
                held.setdefault(
                    Path(model).stem,
                    PostgresBinding.from_document(binding_document(authored, "postgres")),
                )
    return held


def corpus_binding(stem: str) -> PostgresBinding:
    """The binding the corpus places model ``stem`` under: the first a case or
    an evolution endpoint authors for it, else :data:`TEST_BINDING`."""
    return _corpus_case_bindings().get(stem, TEST_BINDING)
