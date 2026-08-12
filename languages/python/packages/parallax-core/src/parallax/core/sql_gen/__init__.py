"""``parallax.core.sql_gen`` enforcement scope (m-sql).

SQL generation: the read compiler that lowers one flat ``EntityQuery`` into a canonical
``LoweredStatement`` per dialect. Dialect variation enters only through the
injected ``Dialect`` strategy. ``m-sql`` depends on ``m-object-query`` (the query
value), ``m-predicate`` (the selection it carries), and ``m-dialect``.

The seven names below are the whole supported seam; everything else in this
package is private implementation. ``compile_read`` returns a self-contained
:class:`CompiledRead` — statement, root narrow, and row transform together — so
a caller executes and transforms without re-deriving anything from the
query it just compiled. The projection this package emits follows the
canonical slot order of ``m-storage-layout``'s compiled ``TableLayout.columns``,
reached through the Entity and position views over it; ``m-inheritance`` keeps
family semantics — ancestry, applicability, discriminator meaning — and no
longer answers physical shape. Every storage-shaped caller (DDL derivation,
keyed write emission, table read-back) reads those same views, so no consumer
rebuilds a physical order of its own.

That implementation is five private modules, each owning one concern:

* ``_compile`` — the two entry points. Ordinary projection, the shared
  ``order by`` / ``limit`` / read-lock tail, normalization, and
  statement assembly, including the inheritance-family read forms it builds from
  the plans ``_inheritance`` resolves.
* ``_predicate`` — the package's ONE recursive owner. Every descent into a
  predicate happens behind its single ``lower_predicate`` entry point, which
  dispatches over an immutable resolution scope: an entity scope (active entity,
  its alias, and whether the statement aliases its own columns at all) or a
  value-object element scope. It holds the package's only RECURSIVE dispatch over
  the node union, so "where does this node get lowered?" has one answer. (The two
  other ``match`` statement in the package lives in ``_compile`` and selects an
  inheritance plan type rather than descending into a predicate.)
* ``_navigation`` — relationship resolution and correlated-hop planning.
* ``_inheritance`` — table-per-hierarchy and table-per-concrete-subtype
  planning, family projection, tag predicates, and ``familyVariant`` row
  transforms.
* ``_context`` — one statement's shared mutable state, and nothing else: the
  metamodel and dialect it renders against, its ordered bind list, and its alias
  counter. It holds no resolution policy.

The private direction is a strict layer order, machine-enforced by two
hand-written Import Linter contracts in `languages/python/pyproject.toml`
(alongside the generated behavioral-DAG contracts, which remain authoritative
for `m-sql`'s own edges)::

    _compile -> _predicate -> _navigation -> _inheritance -> _context

``_navigation`` and ``_inheritance`` return immutable PLANS and lower nothing,
which is what keeps that graph acyclic instead of mutually recursive: neither
has a road back up into ``_predicate``. Both are handed a NARROWED view of the
scope (:class:`~parallax.core.sql_gen._context.ColumnScope` /
:class:`~parallax.core.sql_gen._context.PlanScope`) that cannot name the bind
list at all, which makes "a plan never binds at planning time" a type rule
rather than a convention — the invariant that keeps a framework-added tag bind
from landing ahead of the user's own. The second contract forbids any private
module from importing this package root.
"""

from __future__ import annotations

from parallax.core.sql_gen._compile import (
    CompiledPredicate,
    CompiledRead,
    LoweredStatement,
    MaterializedReadRow,
    SqlGenError,
    compile_read,
    compile_write_predicate,
)

__all__ = [
    "CompiledPredicate",
    "CompiledRead",
    "LoweredStatement",
    "MaterializedReadRow",
    "SqlGenError",
    "compile_read",
    "compile_write_predicate",
]
