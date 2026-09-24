"""Generate (and check) the import-linter forbidden-edge complement.

Parallax enforces the module dependency DAG in Python with import-linter
``forbidden`` contracts. Rather than hand-maintain them, this tool derives them
from the single source of truth — the fenced ``dependency-graph`` block in
``core/spec/modules.md`` — mapped onto Python enforcement scopes and joined with
the Python-only first-party grants ``spec/python.md`` §7 declares, computes each
production scope's transitive dependency closure, and emits the *complement*:
every production scope pair the closure does not permit becomes a forbidden
import. This rejects illegal non-edges, not merely wrong-direction edges (a
``layers`` contract cannot).

§7 states its side of that derivation as four strict tables, one per relation,
and this tool restates each relation once so that the two can be compared:

* behavioral module to enforcement scope — :data:`MODULE_SCOPE`;
* enforcement scope to its allowed direct first-party dependencies, the edges
  no module tag carries — :data:`PYTHON_FIRST_PARTY_GRANTS`;
* restricted external package to the scopes that may import it directly —
  :data:`RESTRICTED_EXTERNAL_GRANTS`;
* child scope to its parent and import policy — :data:`CHILD_SCOPES`.

Every run parses all four tables and compares each with its declaration before
anything is derived. Editing a table alone, or a declaration alone, fails
generation, so ``--write`` can never regenerate past a disagreement with §7.

§7 declares the child topology as a relation of its own — each child scope's
parent and its import policy, ``ordinary``, ``sealed``, or ``isolated`` —
restated here as :data:`CHILD_SCOPES` and parity-checked row by row. Isolation
is generated: an isolated child joins the target universe every row draws from,
so that policy shapes almost every contract emitted here. Sealing generates
nothing at all. What neither policy can express is the edge running between a
scope and its own ancestors, which every contract skips as an overlap;
``tools/check_scope_ownership.py`` closes that half over the files, reading the
same table. So parent and policy are compared exactly, and declaring a child in
§7 alone — or holding it here alone, under another parent, or under another
policy — fails here rather than leaving one declaration promising a guarantee
the other no longer carries.

A forbidden row is the complement of a *closure*, so a scope is never forbidden
what its own grants reach transitively. A scope that exists in order to stay
clear of some boundary therefore has to be granted narrowly enough that the
boundary falls outside its closure — the read preflight seam grants the Object
Query scope rather than the Entity frontend that re-exports its typed surface,
for exactly that reason — rather than granted widely and excepted afterwards.

The core conformance-family exception (``modules.md``) is encoded structurally:
conformance scopes (``parallax.conformance.*``) are exempt on the *importing*
side (they may harness any behavioural scope), while every production scope is
forbidden from importing any conformance scope.

A *restricted external* package — the Pydantic substrate beneath an Entity
value, the Psycopg driver beneath the Postgres adapter — becomes one
``forbidden`` contract sourced from every production scope
:data:`RESTRICTED_EXTERNAL_GRANTS` does not grant it, direct imports only: a
scope granted a first-party scope that itself imports the package reaches it
through that scope and never names it, which is what keeps Snapshot free of
Pydantic while it reaches Entity values.

Usage
-----
* ``python tools/check_dag_sync.py``            verify committed contracts (default)
* ``python tools/check_dag_sync.py --check``    verify committed contracts (explicit)
* ``python tools/check_dag_sync.py --write``    regenerate the contracts in place

Default mode verifies and exits non-zero on any drift, so the same command backs
both the local gate and CI.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import deque
from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

_TOOL = "tools/check_dag_sync.py"
_HERE = Path(__file__).resolve()
_PY_ROOT = _HERE.parents[1]
_REPO_ROOT = _HERE.parents[3]
MODULES_MD = _REPO_ROOT / "core" / "spec" / "modules.md"
PYTHON_MD = _PY_ROOT / "spec" / "python.md"
PYPROJECT = _PY_ROOT / "pyproject.toml"

_BEGIN = "# >>> check_dag_sync.py: BEGIN GENERATED IMPORT-LINTER CONTRACTS >>>"
_END = "# <<< check_dag_sync.py: END GENERATED IMPORT-LINTER CONTRACTS <<<"

# Behavioural module tag -> Python enforcement scope (spec/python.md §7's
# behavioral-scope table, less the one pytest-bounded row below).
MODULE_SCOPE: Mapping[str, str] = {
    "m-core": "parallax.core.base",
    "m-wire": "parallax.core.wire",
    "m-metamodel": "parallax.core.metamodel",
    "m-edit": "parallax.core.entity._edit",
    "m-model-formation": "parallax.core.model_formation",
    "m-descriptor": "parallax.descriptor",
    "m-model-evolution": "parallax.evolution.model_evolution",
    "m-schema-delta": "parallax.evolution.schema_delta",
    "m-pk-gen": "parallax.core.pk_gen",
    "m-inheritance": "parallax.core.inheritance",
    "m-storage-layout": "parallax.core.storage_layout",
    "m-value-object": "parallax.core.value_object",
    "m-document-codec": "parallax.core.document_codec",
    "m-relationship": "parallax.core.relationship",
    "m-predicate": "parallax.core.predicate",
    "m-object-query": "parallax.core.object_query",
    "m-sql": "parallax.core.sql_gen",
    "m-dialect": "parallax.core.dialect",
    "m-db-port": "parallax.core.db_port",
    "m-db-error": "parallax.core.db_error",
    "m-unit-work": "parallax.core.unit_work",
    "m-read-lock": "parallax.core.read_lock",
    "m-auto-retry": "parallax.core.auto_retry",
    "m-execution-authority": "parallax.snapshot.handle._execution_authority",
    "m-execution-lifecycle": "parallax.core.execution_lifecycle",
    "m-opt-lock": "parallax.core.opt_lock",
    "m-temporal-read": "parallax.core.temporal_read",
    "m-txtime-write": "parallax.core.txtime_write",
    "m-bitemp-write": "parallax.core.bitemp_write",
    "m-batch-write": "parallax.core.batch_write",
    "m-navigate": "parallax.core.navigate",
    "m-deep-fetch": "parallax.core.deep_fetch",
    # The tag maps to the read-RESULT module rather than to the row-to-graph
    # package: `m-snapshot-read --> m-execution-lifecycle` reaches `m-sql`, and a
    # forbidden row is the complement of a closure, so granting that package the
    # provenance edge would hand every consumer of the row-to-graph surface SQL
    # generation with it.
    "m-snapshot-read": "parallax.snapshot._read_result",
    "m-case-format": "parallax.conformance.case_format",
    "m-conformance-adapter": "parallax.conformance.cli",
}

# The behavioral modules whose enforcement scope is a pytest collection boundary
# rather than a `parallax` package. import-linter grades none of them, so
# MODULE_SCOPE omits them; §7 still carries a row for each, because the core
# template requires a row per claimed module, and parity requires each row as
# this table spells it.
PYTEST_BOUNDED_SCOPES: Mapping[str, str] = {"m-api-conformance": "tests.api"}

# The write-execution child cluster (`_family`, `_keyed_sql`, `_write_lowering`)
# is enforced as ONE group: the three modules share one §7 row, which names all
# three, rather than each declaring its own. Grouping is deliberate — helpers
# move between the cluster's modules as the lowering pipeline evolves, and a
# per-module row would turn every such internal move into a spec edit. The
# group boundary is what carries the enforcement value: none of the three may
# reach the read side (`m-snapshot-read`, `m-deep-fetch`, `m-navigate`,
# `parallax.core.entity`).
_LOWERING_GROUP_DEPS: frozenset[str] = frozenset(
    {
        "parallax.core.base",
        "parallax.core.wire",
        "parallax.core.metamodel",
        "parallax.core.inheritance",
        "parallax.core.storage_layout",
        "parallax.core.document_codec",
        "parallax.core.temporal_read",
        "parallax.core.dialect",
        "parallax.core.db_port",
        "parallax.core.sql_gen",
        "parallax.core.unit_work",
        "parallax.core.opt_lock",
        "parallax.core.txtime_write",
        "parallax.core.bitemp_write",
    }
)

# Enforcement scope -> the first-party scopes it may import directly beyond
# whatever its module tag's `modules.md` edges already carry: every support
# scope, which has no tag and so no edge anywhere else, and each behavioural
# scope that needs a Python-only edge no language-neutral tag can state. A
# behavioural scope with no such supplement is absent; an empty value is kept
# only where the emptiness is itself enforced. spec/python.md §7's first-party
# support table is read back and compared with this by
# :func:`check_first_party_support_parity`.
PYTHON_FIRST_PARTY_GRANTS: Mapping[str, frozenset[str]] = {
    # A credential provider is a LEAF beside the adapters: it produces
    # configuration a composition root hands to whichever adapter it selected,
    # so it is granted the port that defines the Credential Source seam and
    # nothing else. Granting no adapter is the whole of what this row enforces —
    # an application that never reaches a database over Postgres must be able to
    # install this provider without the driver arriving with it.
    "parallax.aws": frozenset({"parallax.core.db_port"}),
    # The engine-specific leaf of that provider, and the only part of it granted
    # an adapter. Composing a `PostgresAdapter` is producing configuration for a
    # composition root, not layering a runtime above the seam, so the grant is
    # wider than its parent's — and confining it to this one child is what keeps
    # the row above enforceable rather than decorative.
    "parallax.aws.postgres": frozenset({"parallax.core.db_port", "parallax.postgres"}),
    # The standard-library-only projection three scopes share. It grants
    # nothing, which is the whole of what it enforces: a detached diagnostic
    # value must be reachable from the database port, the execution lifecycle,
    # and the resource contracts between them without any of those inheriting
    # the others' edges.
    "parallax.core.diagnostics": frozenset(),
    "parallax.core.db_port": frozenset({"parallax.core.diagnostics"}),
    "parallax.core.execution_lifecycle": frozenset({"parallax.core.diagnostics"}),
    "parallax.core._formation_profile": frozenset(
        {
            "parallax.core.metamodel",
            "parallax.core.model_formation",
            "parallax.core.inheritance",
            "parallax.core.storage_layout",
            "parallax.core.value_object",
            "parallax.core.relationship",
            "parallax.core.temporal_read",
            "parallax.core.opt_lock",
        }
    ),
    "parallax.descriptor._hub": frozenset({"parallax.core.entity"}),
    "parallax.core.entity": frozenset(
        {
            "parallax.core.base",
            "parallax.core.metamodel",
            "parallax.core.inheritance",
            "parallax.core.relationship",
            "parallax.core.predicate",
            "parallax.core.object_query",
            "parallax.core.temporal_read",
            "parallax.core.document_codec",
            "parallax.core._formation_profile",
        }
    ),
    # Query authoring reaches no model: an Attribute Expression carries the
    # member its descriptor installed and a Relationship Path composes its own
    # segments, so the values a developer builds state their rules from accepted
    # metadata alone. Granting neither model formation nor any whole-model
    # semantic view is what makes that provable rather than asserted. The
    # document codec contributes only the member-local authored-document walk;
    # it resolves no Entity position or model fact.
    "parallax.core.entity._expressions": frozenset(
        {
            "parallax.core.base",
            "parallax.core.document_codec",
            "parallax.core.wire",
            "parallax.core.metamodel",
            "parallax.core.predicate",
            "parallax.core.object_query",
        }
    ),
    # The physical backing beneath a published value — the publication plan, the
    # compact slot, the tuple and its bitmap, both Adapters, and the framework
    # root that answers Pydantic for a value's instance state — is scoped apart
    # from the declaration engine that builds a class and the writer that
    # publishes one. Granting it two siblings and nothing else is what forces a
    # publication plan to ARRIVE as plain data rather than be derived here: a
    # scope that could reach the model would grow a second declaration engine
    # inside the module that owns the representation. The second grant is the seam
    # that reaches a value's real storage, which the presentation is layered
    # directly over: what a published value answers for `__dict__` is derived
    # here, and what lies underneath it is read there.
    "parallax.core.entity._instance_state": frozenset(
        {
            "parallax.core.entity._construction_input",
            "parallax.core.entity._pydantic_storage",
        }
    ),
    # The sentinels a positional construction input spells, and the opaque handle a
    # relationship position names a node by, are read by the layout side, by a
    # runtime that lays a stored row out against one, by the writer, by the
    # descriptors that answer a member read, and by the backing above — scopes that
    # deliberately cannot reach one another. Housing them in a scope granted nothing
    # is what lets every one of them reach the same value without reaching through a
    # peer, and what keeps a row's producer unable to reach the writer, `construct`,
    # or model formation.
    "parallax.core.entity._construction_input": frozenset(),
    # A value's own attribute storage, reached past every name a class body can
    # bind. What it reaches is Pydantic's own slot descriptor and nothing else, so
    # a first-party import of any kind would mean it had grown a second job — which
    # is what a grant row of nothing states and enforces.
    "parallax.core.entity._pydantic_storage": frozenset(),
    # The exact-model member layouts are a pure function of the accepted
    # Metamodel, so they are scoped apart from the frontend that owns them and
    # granted only the facets a layout is derived from. Granting them narrowly is
    # what lets row-to-graph materialization take the layouts alone: the parent
    # frontend reaches model formation, Object Query, and — through
    # `_formation_profile -> opt_lock -> unit_work` — the Database Port, none of
    # which a positional member row depends on.
    "parallax.core.entity._layout": frozenset(
        {
            "parallax.core.metamodel",
            "parallax.core.inheritance",
            "parallax.core.relationship",
        }
    ),
    # The typed Object Query is generic over Entity Classes, so it reaches the
    # Entity frontend for the descriptor values a clause call is written with. Its
    # parent package must stay reachable by every execution module that realizes a
    # clause, and none of those may reach that frontend — so the widening is
    # declared here and the parent's own interface never imports this module.
    "parallax.core.object_query._fluent": frozenset(
        {
            "parallax.core.base",
            "parallax.core.metamodel",
            "parallax.core.predicate",
            "parallax.core.entity",
        }
    ),
    # The Snapshot slice's own node-inspection surface is scoped apart from both
    # snapshot packages: it reads a node's loaded views, pin, milestone edge, and
    # retained Read Origin through the advanced Entity seam and nothing else, so
    # its row proves it reaches no driver, no read planner, no SQL, and no
    # dialect. The Database Port is NOT one of those: the granted Entity frontend
    # reaches it through `_formation_profile -> opt_lock -> unit_work -> db_port`,
    # and a forbidden row is the complement of a closure, so this row admits it —
    # `parallax.snapshot.handle._preflight` below is the scope whose grant is
    # narrowed for exactly the boundary this one cannot state.
    "parallax.snapshot._inspection": frozenset(
        {
            "parallax.core.entity",
            "parallax.core.metamodel",
            "parallax.core.inheritance",
            "parallax.core.relationship",
            "parallax.core.temporal_read",
        }
    ),
    # The page node a streamed read advances by: pure, and scoped apart from the
    # handle that consumes it because the page statement is a cross-language
    # contract rather than one implementation's helper. Its grants are what
    # composing an ordinary Object Query needs and nothing else, so the scope
    # row is what proves a continuation reaches no port, no SQL generation, no
    # dialect, and no materialization.
    "parallax.core.continuation": frozenset(
        {
            "parallax.core.metamodel",
            "parallax.core.inheritance",
            "parallax.core.predicate",
            "parallax.core.object_query",
            "parallax.core.temporal_read",
            "parallax.core.wire",
        }
    ),
    "parallax.snapshot.handle": frozenset(
        {
            "parallax.core.continuation",
            "parallax.snapshot.materialize",
            "parallax.snapshot._read_result",
            "parallax.snapshot._inspection",
            "parallax.core.entity",
            "parallax.core.base",
            "parallax.core.wire",
            "parallax.core.metamodel",
            "parallax.core.predicate",
            "parallax.core.inheritance",
            "parallax.core.storage_layout",
            "parallax.core.temporal_read",
            "parallax.core.deep_fetch",
            "parallax.core.navigate",
            "parallax.core.dialect",
            "parallax.core.db_port",
            "parallax.core.sql_gen",
            "parallax.core.unit_work",
            "parallax.core.read_lock",
            "parallax.core.auto_retry",
            "parallax.core.execution_lifecycle",
            "parallax.core.opt_lock",
            "parallax.core.batch_write",
            "parallax.core.txtime_write",
            "parallax.core.bitemp_write",
        }
    ),
    "parallax.snapshot.handle._materialization": frozenset(
        {
            "parallax.core.continuation",
            "parallax.snapshot.materialize",
            "parallax.snapshot._read_result",
            "parallax.snapshot._inspection",
            "parallax.core.entity",
            "parallax.core.metamodel",
            "parallax.core.inheritance",
            "parallax.core.temporal_read",
            "parallax.core.db_port",
            "parallax.core.sql_gen",
            "parallax.core.read_lock",
            "parallax.core.execution_lifecycle",
        }
    ),
    # The one Python-only support edge the BEHAVIOURAL `m-snapshot-read` scope
    # carries: the row-to-graph package it publishes results from is a Python
    # scope with no language-neutral module tag, so `modules.md` cannot state the
    # edge and §7 is its only declaration. Every other `m-snapshot-read` edge
    # stays in `modules.md`, and this table's grants are unioned with those.
    "parallax.snapshot._read_result": frozenset({"parallax.snapshot.materialize"}),
    # The row-to-graph half of `m-snapshot-read`, scoped apart from the read
    # result `parallax.snapshot._read_result` publishes. It holds every
    # `m-snapshot-read` edge EXCEPT `m-execution-lifecycle`, plus the layout a
    # projection is laid out against and the sentinel scope its absent positions
    # are spelled with, neither of which has a language-neutral module tag either.
    # Withholding the provenance edge here keeps `m-sql`, `m-db-error`,
    # `m-auto-retry`, and `m-dialect` outside this representation scope. The
    # separately declared `parallax.snapshot.handle._materialization` seam grants
    # the execution dependencies it owns without widening Page representation.
    "parallax.snapshot.materialize": frozenset(
        {
            "parallax.core.entity",
            "parallax.core.entity._construction_input",
            "parallax.core.entity._layout",
            "parallax.core.deep_fetch",
            "parallax.core.document_codec",
            "parallax.core.metamodel",
            "parallax.core.inheritance",
            "parallax.core.relationship",
            "parallax.core.temporal_read",
            "parallax.core.wire",
            "parallax.snapshot._inspection",
        }
    ),
    # The read gate is scoped apart from its own package so the generated
    # contract proves what its module docstring claims: a preflight that resolves
    # a target and validates a query names no SQL generation, no dialect, no
    # Database Port, no deep-fetch planning and no materialization. The grant is
    # the Object Query scope rather than the Entity frontend precisely so
    # the Database Port falls OUTSIDE this row's closure: the frontend package
    # reaches one through `_formation_profile -> opt_lock -> unit_work ->
    # db_port`, and a forbidden row is the complement of a closure, so a grant
    # wide enough to include that chain could never forbid its endpoint.
    "parallax.snapshot.handle._preflight": frozenset(
        {
            "parallax.core.metamodel",
            "parallax.core.predicate",
            "parallax.core.object_query",
        }
    ),
    # The read composition both Handles delegate to, scoped apart from its
    # package so the generated contract carries what a read ladder reaches: the
    # query it lowers, the plan a stream is delivered against, the result it
    # publishes, the port it executes over, the unit of work a participating
    # read force-flushes, and the lifecycle activities it opens. Batch writes,
    # Transaction-Time writes and Bitemporal writes fall outside this closure,
    # which is the exclusion the row is FOR — the parent scope is granted all
    # three.
    #
    # Two grants a reader might expect to be absent are load-bearing.
    # `parallax.snapshot._inspection` closes the chain the read executor opens
    # through the materializer child, which the row would otherwise report at
    # its far end; and `m-execution-lifecycle` carries `m-auto-retry`,
    # `m-sql` and `m-db-error` into the closure through `modules.md`'s own
    # edges, so retry and SQL generation are inherited here rather than
    # forbidden. Write lowering is a sibling child scope, which the general
    # target set excludes, so no row can name it either way.
    "parallax.snapshot.handle._read_scope": frozenset(
        {
            "parallax.core.entity",
            "parallax.core.continuation",
            "parallax.snapshot._read_result",
            "parallax.snapshot._inspection",
            "parallax.core.object_query",
            "parallax.core.temporal_read",
            "parallax.core.db_port",
            "parallax.core.unit_work",
            "parallax.core.read_lock",
            "parallax.core.opt_lock",
            "parallax.snapshot.handle._execution_authority",
            "parallax.core.execution_lifecycle",
        }
    ),
    # The keyed write ingress, scoped apart from its package so the generated
    # contract carries what a keyed write reaches: the value and the metadata it
    # resolves an Entity from, the document codec whose one comparison answers
    # its effective change set, the temporal vocabulary its pin and window are
    # stated in, the unit of work it claims and buffers into, and the lifecycle
    # whose re-entry it refuses first. A keyed write addresses a row its caller
    # already holds, so the read half of the parent scope falls outside this
    # closure — row-to-graph materialization, the read result, and the read lock
    # are each forbidden here and each granted to the parent — and so do the
    # three write policies, which lowering owns in its own sibling child scopes.
    #
    # `m-db-port`, `m-deep-fetch` and `m-navigate` are deliberately NOT among
    # those exclusions, and the row does not claim them: `modules.md` routes the
    # port through `m-execution-lifecycle` and the two traversal modules through
    # `parallax.core.entity`, and a forbidden row is the complement of a
    # closure, so each rides in whatever this composition itself imports. What
    # the row says about them is that this scope inherits them, not that they are
    # forbidden. `_write_inputs`, `_family` and `_predicate_writes` are modules
    # of the parent package rather than declared scopes, so no row can name any
    # of the three either way.
    "parallax.snapshot.handle._keyed_writes": frozenset(
        {
            "parallax.core.entity",
            "parallax.snapshot._inspection",
            "parallax.core.metamodel",
            "parallax.core.document_codec",
            "parallax.core.temporal_read",
            "parallax.core.unit_work",
            "parallax.core.execution_lifecycle",
        }
    ),
    # The refusal leaf's emptiness IS its contract: `_preflight` and `_family`
    # raise one error class while their scopes grant disjoint dependencies, so
    # either naming the other would drag in a scope the importer may not reach.
    # A zero-grant scope forbids every first-party scope outside its own package
    # AND every sibling child scope inside it, and `tools/check_scope_ownership.py`
    # adds the file-level fact no scope table can carry: no import-free module
    # sits beside it undeclared. What keeps the two consumers legal is their own
    # rows — a dependency added here would break the row of whichever consumer
    # is not already granted it.
    "parallax.snapshot.handle._errors": frozenset(),
    "parallax.snapshot.handle._family": _LOWERING_GROUP_DEPS,
    "parallax.snapshot.handle._keyed_sql": _LOWERING_GROUP_DEPS,
    "parallax.snapshot.handle._write_lowering": _LOWERING_GROUP_DEPS,
    # Write-observation retention is scoped apart from its own package so the
    # generated contract carries the OUTWARD half of its module docstring's
    # account: what a read retains is a pure function of accepted metadata, the
    # columns a row observed, and Unit Work's own observation vocabulary,
    # resolved through the family leaf. The half facing INTO the package is
    # beyond any contract sourced here and is graded by its SEALED policy below.
    # Measured against the PARENT grant this row replaces, nine of its
    # twenty-five grants fall outside this row's closure — `continuation`,
    # `parallax.snapshot.materialize`, `parallax.snapshot._read_result`,
    # `parallax.snapshot._inspection`,
    # `parallax.core.entity` (private `_declaration` / `_entity` with it),
    # `read_lock`, `auto_retry`, `execution_lifecycle` and `batch_write` — so
    # retention reaches neither the read's own machinery nor an Entity frontend,
    # and can never grow the third accepted private-Entity reach its keyed
    # sibling's two would otherwise leave room for.
    #
    # Two claims a reader might expect are NOT made, for one shape of reason.
    # `m-deep-fetch` and `m-navigate` stay inside the closure although nothing
    # here names them: `_family`'s own grant reaches `m-sql`, which reaches both.
    # Port- and SQL-freedom goes the same way — `m-unit-work` reaches
    # `m-db-port`, and `_family` names `sql_gen`, `dialect` and `db_port`
    # outright — so `_preflight`'s property cannot be replicated short of
    # splitting `_family`, which no decision here takes.
    #
    # The complement this row generates is therefore identical to the lowering
    # group's, because `_family` is retention's only handle dependency and its
    # grant already covers the other three. What the row carries is the
    # DECLARATION: the file resolves here rather than to the parent's twenty-five
    # scopes, and a reach outside the closure these four open has to widen this
    # entry to land. What this row rejects that the parent's permits is those
    # nine grants together with what only they reached — `_formation_profile`
    # and `value_object` behind the Entity frontend, `db_error` behind the
    # retrying execution path. INSIDE the closure the four grants open, the row
    # says nothing.
    #
    # The one-way rule — retention never names the read executor — is the half no
    # contract sourced here can state: `compute_forbidden` subtracts a scope's
    # ancestors unconditionally, import-linter's forbidden contracts are
    # package-scoped on both sides, and the read executor lives in the parent
    # scope, so a row naming it overlaps its own source and is silently skipped.
    # That is what the SEALED policy below is for: `check_scope_ownership.py` walks
    # this scope's files and refuses every import into `parallax.snapshot.handle`
    # no grant covers, so `_read`, `_write_inputs`, and every sibling but the
    # granted `_family` are rejected over the source rather than left to prose.
    # A prepared Model Selection is process-local and holds no transaction,
    # connection, Clock, or Execution Lifecycle Provider. Granting the scope the
    # Entity frontend — for the Domain Model, the cataloged model, the row
    # codec, and the graph construction a selection retains — and the unit of
    # work — for the Write Planner — and nothing else is what makes the first
    # three of those absences structural rather than asserted: no attempt, no
    # port, and no activity is nameable here. Sealed, because the handle package
    # beside it holds every one of them.
    "parallax.snapshot.handle._publication": frozenset(
        {
            "parallax.core.entity",
            "parallax.core.unit_work",
        }
    ),
    "parallax.snapshot.handle._retention": frozenset(
        {
            "parallax.core.metamodel",
            "parallax.core.unit_work",
            "parallax.core.temporal_read",
            "parallax.snapshot.handle._family",
        }
    ),
    "parallax.postgres": frozenset(
        {
            "parallax.core.base",
            "parallax.core.wire",
            "parallax.core.db_port",
            "parallax.core.db_error",
            "parallax.core.dialect",
        }
    ),
}

ChildPolicy = Literal["ordinary", "sealed", "isolated"]
_CHILD_POLICIES: tuple[ChildPolicy, ...] = get_args(ChildPolicy)


@dataclass(frozen=True)
class ChildScope:
    """One row of §7's child-scope table: the parent a child is nested inside
    and the import policy governing it.

    ``ordinary`` — the child's generated row is the whole of its enforcement.

    ``isolated`` — a grant on the PARENT does not carry the child. A forbidden
    row is the complement of a closure over whole scopes, so a scope granted a
    parent may ordinarily import anything nested inside it; an isolated child is
    the exception, forbidden to every production scope that neither contains it
    nor is contained by it, whatever those scopes reach. That is what turns "no
    production path imports this" from a fact about the grant table — which
    states only what a scope MAY import, never what it may not — into a rejected
    import. The one containment a contract cannot state is a scope importing its
    own descendant: import-linter silently skips a forbidden module overlapping
    the contract's source package, so the parent's row can never name its own
    child, and ``tools/check_scope_ownership.py`` closes that edge over the files.

    ``sealed`` — the child's grant row is the whole of what it may import INSIDE
    its own parent package as well as outside it. A row can neither forbid nor
    except what sits inside its own source package, so it refuses a neighbour
    only through the chain that leaves it: reaching one whose own closure escapes
    the row is reported at whatever it escapes to. A neighbour reaching nothing
    the row does not already permit leaves no chain to report, and nothing
    rejects it — so without this policy, whether a narrow grant is the whole
    story depends on what the modules beside it happen to import. A sealed child
    declares that its grants ARE the whole story, and
    ``tools/check_scope_ownership.py`` refuses the rest over the files: the same
    division of labour isolation runs the other way round.
    """

    parent: str
    policy: ChildPolicy


# Enforcement scopes nested inside another scope, each mapped to that parent and
# to its policy. The relation is declared rather than derived from dotted-path
# prefixes so that two independent consumers must agree about it:
#
# * this generator emits a child as a contract *source*, and as a forbidden
#   *target* only in a SIBLING's zero-grant row (:func:`scope_siblings`) or —
#   for an isolated child — in every row that overlaps it nowhere. Naming a
#   child in its own parent's ``forbidden_modules`` would overlap the parent's
#   source package, which import-linter >= 2.12 silently skips — the contract
#   would look present and enforce nothing — and naming it in an unrelated
#   scope's row would only restate the parent's own entry. A sibling overlaps
#   neither way, which is what lets a scope granted nothing forbid it.
# * ``tools/check_scope_ownership.py`` allows a production file to resolve to
#   more than one scope only along a chain declared here. A nested scope added
#   to :data:`PYTHON_FIRST_PARTY_GRANTS` but not registered here therefore
#   fails the ownership check instead of silently producing that skipped
#   contract. That tool also reads this table to find the siblings a zero-grant
#   row names, and fails when a module beside one is import-free and undeclared
#   — a sibling shape such a row cannot reach — and takes from it the scopes
#   whose sealed or isolated half it grades over the files.
CHILD_SCOPES: Mapping[str, ChildScope] = {
    # Installing the credential provider must install no adapter, so the one
    # module composing one has to stay unreachable from everything that does
    # not select it. The parent's row excepts this child's adapter edge by
    # name, and an exception withdraws every chain running through that edge —
    # so the parent's own row could no longer report a module of `parallax.aws`
    # reaching the adapter THROUGH this child. Isolation is what rejects that
    # import instead, over the files, in the one place a contract cannot look.
    "parallax.aws.postgres": ChildScope(parent="parallax.aws", policy="isolated"),
    # The four publication-side children of the Entity frontend are sealed
    # because their whole reason to exist is what they cannot reach: the
    # construction-input vocabulary both a row's producer and its reader are
    # stated in must reach nothing at all, the backing beneath a published value
    # must reach neither the declaration engine nor the writer, a layout is a
    # pure function of accepted metadata, and a value's own attribute storage
    # must reach nothing either — every one of which sits in the parent package
    # beside them.
    "parallax.core.entity._construction_input": ChildScope(
        parent="parallax.core.entity", policy="sealed"
    ),
    "parallax.core.entity._edit": ChildScope(parent="parallax.core.entity", policy="ordinary"),
    "parallax.core.entity._expressions": ChildScope(
        parent="parallax.core.entity", policy="ordinary"
    ),
    "parallax.core.entity._instance_state": ChildScope(
        parent="parallax.core.entity", policy="sealed"
    ),
    "parallax.core.entity._layout": ChildScope(parent="parallax.core.entity", policy="sealed"),
    "parallax.core.entity._pydantic_storage": ChildScope(
        parent="parallax.core.entity", policy="sealed"
    ),
    "parallax.core.object_query._fluent": ChildScope(
        parent="parallax.core.object_query", policy="ordinary"
    ),
    "parallax.descriptor._hub": ChildScope(parent="parallax.descriptor", policy="ordinary"),
    "parallax.snapshot.handle._errors": ChildScope(
        parent="parallax.snapshot.handle", policy="ordinary"
    ),
    "parallax.snapshot.handle._execution_authority": ChildScope(
        parent="parallax.snapshot.handle", policy="sealed"
    ),
    "parallax.snapshot.handle._family": ChildScope(
        parent="parallax.snapshot.handle", policy="ordinary"
    ),
    "parallax.snapshot.handle._keyed_sql": ChildScope(
        parent="parallax.snapshot.handle", policy="ordinary"
    ),
    "parallax.snapshot.handle._keyed_writes": ChildScope(
        parent="parallax.snapshot.handle", policy="ordinary"
    ),
    "parallax.snapshot.handle._materialization": ChildScope(
        parent="parallax.snapshot.handle", policy="ordinary"
    ),
    "parallax.snapshot.handle._preflight": ChildScope(
        parent="parallax.snapshot.handle", policy="ordinary"
    ),
    # Model publication is sealed for what a prepared selection must not hold:
    # the demarcation, the read composition, the keyed write ingress, and every
    # other module of the handle package carries a connection, an attempt, or an
    # activity, and a selection that could name one would no longer be
    # process-local state a Serving Model can hand to any execution. The seal is
    # what grades that absence over the package the selection lives in.
    "parallax.snapshot.handle._publication": ChildScope(
        parent="parallax.snapshot.handle", policy="sealed"
    ),
    "parallax.snapshot.handle._read_scope": ChildScope(
        parent="parallax.snapshot.handle", policy="ordinary"
    ),
    # Write-observation retention is sealed for the same reason read the other
    # way: the read executor DRIVES it, and the dependency going only that way is
    # what lets a row's evidence be a pure function of the row. That executor is
    # a module of the parent package, so no contract sourced at the child can
    # reject that import and the seal is where the rule is GRADED rather than
    # merely stated — and it holds the rest of the package out with it, which is
    # what makes retention's four grants its whole reach rather than its whole
    # intent.
    "parallax.snapshot.handle._retention": ChildScope(
        parent="parallax.snapshot.handle", policy="sealed"
    ),
    "parallax.snapshot.handle._write_lowering": ChildScope(
        parent="parallax.snapshot.handle", policy="ordinary"
    ),
}


def scopes_with_policy(policy: ChildPolicy) -> frozenset[str]:
    """The declared child scopes :data:`CHILD_SCOPES` places under ``policy``."""
    return frozenset(child for child, declared in CHILD_SCOPES.items() if declared.policy == policy)


# The namespace every enforcement scope and every import-linter root sits
# under; a distribution's top package is its second component.
FIRST_PARTY_NAMESPACE: str = "parallax"

# Every production scope is forbidden from importing *any* conformance scope
# (python.md §7). Rather than enumerate the conformance subtree — which silently
# leaves a newly added conformance module (`.adapter`, `.claim`, `.api_suite`, …)
# importable — the whole package is forbidden as one edge; import-linter treats a
# package forbidden module as covering all its descendants (`as_packages`).
# The conformance scopes declared beneath it are exempt on the *importing*
# side: a declared scope inside this root is not a production scope, so no
# forbidden contract is sourced from it.
CONFORMANCE_ROOT: str = "parallax.conformance"


def declared_first_party_scopes() -> frozenset[str]:
    """Every enforcement scope §7 declares: the behavioral mapping's scopes and
    the first-party support table's, conformance scopes included."""
    return frozenset(MODULE_SCOPE.values()) | frozenset(PYTHON_FIRST_PARTY_GRANTS)


def is_in_scope(module: str, scope: str) -> bool:
    """Whether ``module`` is ``scope`` or something nested inside it."""
    return module == scope or module.startswith(f"{scope}.")


def production_scopes() -> frozenset[str]:
    """The declared scopes outside :data:`CONFORMANCE_ROOT`: the ones a
    contract is sourced from, and the only owners a restricted external may
    be granted to beside the conformance root itself."""
    return frozenset(
        scope for scope in declared_first_party_scopes() if not is_in_scope(scope, CONFORMANCE_ROOT)
    )


def enforcement_root(scope: str) -> str:
    """The distribution's top package ``scope`` sits under, ``parallax.<pkg>``."""
    parts = scope.split(".")
    if len(parts) < 2 or parts[0] != FIRST_PARTY_NAMESPACE:
        raise ValueError(
            f"enforcement scope is not inside a {FIRST_PARTY_NAMESPACE} package: {scope!r}"
        )
    return ".".join(parts[:2])


def root_packages() -> tuple[str, ...]:
    """The import-linter roots, sorted: the top package of every declared scope
    and of the conformance root, so a first scope in a new distribution adds
    that distribution without an inventory edit."""
    scopes = declared_first_party_scopes() | {CONFORMANCE_ROOT}
    return tuple(sorted({enforcement_root(scope) for scope in scopes}))


# Restricted external package -> the scopes that may import it DIRECTLY
# (spec/python.md §7's restricted-external table). Keys are top-level import
# names, the only granularity import-linter forbids an external at. A grant is a
# permission to name the package, not a first-party edge: it enters no closure,
# a parent's grant does not carry its declared children, and first-party
# reachability confers nothing — `parallax.core.entity._pydantic_storage` owns
# `pydantic` while its first-party row grants nothing at all.
#
# The Entity children are granted one by one because each imports the substrate
# for its own reason: the frontend for its metaclass and validators, `_edit` for
# the `BaseModel` bound it derives over, `_instance_state` for the root that
# answers Pydantic for a value's state (and `pydantic_core` for the undefined
# sentinel it compares against), `_pydantic_storage` for the slot descriptors it
# reaches past every binding. `_construction_input`, `_expressions`, and
# `_layout` are not granted, and so are contract sources of their own.
#
# `botocore` is granted to the AWS credential provider alone, both of its
# scopes by name because a parent's grant does not carry its declared children
# and the engine-specific slice names a botocore session in its own signature.
# It is the AWS credential chain the provider needs rather than the token, which
# is signed locally, and no other scope has any business resolving an AWS
# identity. That slice is granted `psycopg` too, for the canonical composer of
# the connection string it hands the adapter; the manifest is untouched by that
# grant, since the driver reaches it through `parallax-postgres`.
#
# The conformance harness is granted `pydantic` for its native edit witnesses —
# fixtures that are deliberately Pydantic models exercising the Entity frontend
# from outside it — and `psycopg` for the driver sessions it opens that no
# application would. Both grants are parity-checked documentation: no contract
# is sourced from a conformance scope, so neither generates anything.
RESTRICTED_EXTERNAL_GRANTS: Mapping[str, frozenset[str]] = {
    "pydantic": frozenset(
        {
            "parallax.core.entity",
            "parallax.core.entity._edit",
            "parallax.core.entity._instance_state",
            "parallax.core.entity._pydantic_storage",
            CONFORMANCE_ROOT,
        }
    ),
    "pydantic_core": frozenset({"parallax.core.entity._instance_state"}),
    "psycopg": frozenset({"parallax.postgres", "parallax.aws.postgres", CONFORMANCE_ROOT}),
    "psycopg_pool": frozenset({"parallax.postgres"}),
    "botocore": frozenset({"parallax.aws", "parallax.aws.postgres"}),
}


_EDGE = re.compile(r"(\S+)\s*-->\s*(\S+)")


def parse_dependency_graph(text: str) -> list[tuple[str, str]]:
    """Extract ``A --> B`` edges from the fenced ``dependency-graph`` block."""
    match = re.search(r"```dependency-graph\n(.*?)\n```", text, re.DOTALL)
    if match is None:
        raise ValueError("no fenced ```dependency-graph``` block found in modules.md")
    edges: list[tuple[str, str]] = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        edge = _EDGE.fullmatch(stripped)
        if edge is None:
            raise ValueError(f"unparseable dependency-graph line: {line!r}")
        edges.append((edge.group(1), edge.group(2)))
    return edges


# The four §7 tables, each opened by its header line; contiguous `|`-prefixed
# lines are its rows. A cell declares only what it spells in backticks, with
# the two bare spellings named below: `_NO_GRANTS` and the child policy word.
_BACKTICKED_ONLY = re.compile(r"`[^`]+`")
# The behavioral-scope table: one row per behavioral module, the module tag in
# the first cell and the enforcement scope owning it in the second.
_BEHAVIORAL_HEADER = "| Behavioral module |"
# The first-party support table: one row per enforcement scope — or per group of
# scopes sharing one grant, every member named in the first cell — and its
# allowed direct first-party dependencies in the second, as module tags or
# scopes. An empty grant is spelled `_NO_GRANTS`, alone.
_FIRST_PARTY_HEADER = "| Enforcement scope |"
_NO_GRANTS = "(none)"
# The restricted-external table: one row per top-level import name, owners in
# the second cell. import-linter forbids an external only as its top-level
# package and squashes every submodule import into that one node, so a dotted
# name would declare a grant nothing could enforce.
_RESTRICTED_EXTERNAL_HEADER = "| Restricted external package |"
_TOP_LEVEL_PACKAGE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# The child-scope table: one row per child, its parent in the second cell and
# its policy, unbackticked, in the third. Parent and policy are properties of one
# declared relationship, which is why the row carries both.
_CHILD_SCOPE_HEADER = "| Child enforcement scope |"


def _table_rows(text: str, header: str, cells: int, label: str) -> list[list[str]]:
    """A §7 table opened by ``header`` as cell lists, separator row dropped."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(header)), None)
    if start is None:
        raise ValueError(f"no §7 {label} table found in spec/python.md")
    rows: list[list[str]] = []
    for line in lines[start + 1 :]:
        if not line.startswith("|"):
            break
        row = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(set(cell) <= set("-: ") for cell in row):
            continue
        if len(row) != cells:
            raise ValueError(f"§7 {label} table row does not have {cells} cells: {line!r}")
        rows.append(row)
    if not rows:
        raise ValueError(f"§7 {label} table has no rows")
    return rows


def _one_backticked(cell: str, label: str, field: str) -> str:
    """The one backticked name a cell holds, and nothing else.

    Text beside the name is refused rather than skipped: it would be read by
    nobody and enforced by nothing here, while a reader counting bare tokens
    could take it for a row of its own.
    """
    if not _BACKTICKED_ONLY.fullmatch(cell):
        raise ValueError(
            f"§7 {label} table: the {field} cell must hold exactly one backticked name "
            f"and nothing else, got {cell!r}"
        )
    return cell.strip("`")


def _backticked_list(cell: str, label: str, field: str) -> list[str]:
    """The comma-separated backticked names a cell holds, and nothing else.

    A cell is a relation's column, not prose: a token that is not backticked
    would be read by nobody and enforced by nothing, so it is refused rather
    than skipped, and an empty cell declares nothing rather than something.
    """
    tokens = [token.strip() for token in cell.split(",")]
    if not all(_BACKTICKED_ONLY.fullmatch(token) for token in tokens):
        raise ValueError(
            f"§7 {label} table: the {field} cell must hold comma-separated backticked "
            f"names, got {cell!r}"
        )
    return [token.strip("`") for token in tokens]


def parse_behavioral_scope_table(text: str) -> dict[str, str]:
    """The behavioral mapping §7 declares: module tag to the enforcement scope
    that owns it, one row per module.

    A scope outside the ``parallax`` namespace is accepted on exactly the rows
    :data:`PYTEST_BOUNDED_SCOPES` names, spelled as it names them: those modules
    are enforced by a pytest collection boundary rather than by import-linter,
    and their rows exist for the core template's row-per-module rule, not for
    generation.
    """
    declared: dict[str, str] = {}
    for module_cell, scope_cell in _table_rows(text, _BEHAVIORAL_HEADER, 2, "behavioral-scope"):
        module = _one_backticked(module_cell, "behavioral-scope", "module")
        scope = _one_backticked(scope_cell, "behavioral-scope", "scope")
        if not module.startswith("m-"):
            raise ValueError(
                f"§7 behavioral-scope table: {module!r} is not a behavioral module tag"
            )
        if module in declared:
            raise ValueError(
                f"§7 behavioral-scope table declares {module!r} more than once; a second "
                "row would replace the first before parity compares it"
            )
        if not scope.startswith("parallax.") and PYTEST_BOUNDED_SCOPES.get(module) != scope:
            raise ValueError(
                f"§7 behavioral-scope table maps {module!r} to {scope!r}, which is neither "
                "a `parallax.*` enforcement scope nor that module's pytest-bounded scope"
            )
        declared[module] = scope
    return declared


def _grants(cell: str, scope: str) -> frozenset[str]:
    """The scopes a first-party support row's dependency cell grants.

    :data:`_NO_GRANTS` alone spells an empty grant; every other token is a
    backticked module tag resolved through :data:`MODULE_SCOPE` or a backticked
    ``parallax.*`` scope. Naming :data:`_NO_GRANTS` beside a real grant is a
    contradiction rather than a wider grant, and a backticked token of neither
    shape is a spec error rather than something to skip — a restricted external
    such as ``psycopg`` is declared by the restricted-external table, never as a
    first-party grant.
    """
    tokens = [token.strip() for token in cell.split(",")]
    if _NO_GRANTS in tokens:
        if len(tokens) == 1:
            return frozenset()
        rest = ", ".join(token for token in tokens if token != _NO_GRANTS)
        _backticked_list(rest, "first-party support", "dependencies")
        raise ValueError(
            f"§7 first-party support row for {scope!r} declares {_NO_GRANTS} beside a real "
            f"grant: {cell!r}"
        )
    grants: set[str] = set()
    for token in _backticked_list(cell, "first-party support", "dependencies"):
        if token.startswith("parallax."):
            grants.add(token)
        elif token.startswith("m-"):
            mapped = MODULE_SCOPE.get(token)
            if mapped is None:
                raise ValueError(
                    f"§7 first-party support row for {scope!r} grants module tag "
                    f"{token!r}, which MODULE_SCOPE does not model"
                )
            grants.add(mapped)
        else:
            raise ValueError(
                f"§7 first-party support row for {scope!r} grants {token!r}, which is "
                "neither a module tag nor a `parallax.*` enforcement scope"
            )
    return frozenset(grants)


def parse_first_party_support_table(text: str) -> dict[str, frozenset[str]]:
    """The first-party support relation §7 declares: enforcement scope to the
    scopes it may import directly beyond its module tag's ``modules.md`` edges.

    A row's scope cell names one or more ``parallax.*`` scopes outright — a
    group sharing one grant names every member — and each scope is declared by
    one row, a second being a contradiction to reject rather than a later
    reading to keep. Every scope a row grants must be one the behavioral mapping
    or this table declares, so a grant can never name a scope no contract is
    sourced from.
    """
    declared: dict[str, frozenset[str]] = {}
    for scope_cell, deps_cell in _table_rows(text, _FIRST_PARTY_HEADER, 2, "first-party support"):
        scopes = _backticked_list(scope_cell, "first-party support", "scope")
        for scope in scopes:
            if not scope.startswith("parallax."):
                raise ValueError(
                    f"§7 first-party support table: {scope!r} is not a `parallax.*` "
                    "enforcement scope"
                )
            if scope in declared:
                raise ValueError(
                    f"§7 first-party support table declares {scope!r} more than once; a "
                    "second row would replace the first before parity compares it"
                )
        grants = _grants(deps_cell, scopes[0])
        for scope in scopes:
            declared[scope] = grants
    known = frozenset(MODULE_SCOPE.values()) | frozenset(declared)
    for scope in sorted(declared):
        unknown = sorted(declared[scope] - known)
        if unknown:
            raise ValueError(
                f"§7 first-party support row for {scope!r} grants scopes no §7 row "
                f"declares: {unknown}"
            )
    return declared


def parse_child_scope_table(text: str) -> dict[str, ChildScope]:
    """The child topology §7 declares: child scope to the parent it is nested
    inside and the policy governing it.

    Every child and every parent must be a declared scope: the ownership walk
    resolves a file along this chain, and both policies beyond ``ordinary`` are
    properties OF a child relationship — one says a grant on the parent does not
    carry the child, the other says the child's grants are complete inside the
    parent's package — so no row can describe a scope nothing declares. A child
    must be nested inside its parent by dotted path, the policy vocabulary is
    closed, and a child is declared by one row: a second row is a contradiction
    rather than a later reading to keep, since silently keeping the last would
    erase exactly the disagreement parity exists to catch.
    """
    scopes = declared_first_party_scopes()
    declared: dict[str, ChildScope] = {}
    for child_cell, parent_cell, policy in _table_rows(text, _CHILD_SCOPE_HEADER, 3, "child-scope"):
        child = _one_backticked(child_cell, "child-scope", "child")
        parent = _one_backticked(parent_cell, "child-scope", "parent")
        if child in declared:
            raise ValueError(
                f"§7 child-scope table declares {child!r} more than once; a second row "
                "would replace the first before parity compares it"
            )
        if child not in scopes:
            raise ValueError(
                f"§7 child-scope table declares {child!r}, which is not a declared "
                "enforcement scope"
            )
        if parent not in scopes:
            raise ValueError(
                f"§7 child-scope table row for {child!r} names an undeclared parent scope "
                f"{parent!r}"
            )
        if not child.startswith(f"{parent}."):
            raise ValueError(
                f"§7 child-scope table row for {child!r}: the child is not nested inside "
                f"its parent {parent!r}"
            )
        if policy not in _CHILD_POLICIES:
            raise ValueError(
                f"§7 child-scope table row for {child!r} states the import policy "
                f"{policy!r}, which is none of {list(_CHILD_POLICIES)}"
            )
        declared[child] = ChildScope(parent=parent, policy=policy)
    return declared


def _grantable_external_owners() -> frozenset[str]:
    """The scopes a restricted external may be granted to: every declared
    production scope, plus the conformance root as one development-only grant."""
    return production_scopes() | {CONFORMANCE_ROOT}


def parse_restricted_external_table(text: str) -> dict[str, frozenset[str]]:
    """The restricted-external ownership §7 declares: top-level import name to
    the scopes granted a direct import of it.

    The package cell holds exactly one backticked top-level identifier, because
    that is the only granularity import-linter forbids an external at; a dotted
    submodule is rejected rather than silently widened to its root. The owners
    cell holds one or more backticked scopes, each a declared production scope
    or :data:`CONFORMANCE_ROOT`: an empty cell would declare a package nobody
    may import — a grant table states permissions, and a package with none
    belongs off the table — and an undeclared owner would grant nothing. One
    row per package, so a second row is a contradiction rather than a wider
    grant.
    """
    owners_universe = _grantable_external_owners()
    declared: dict[str, frozenset[str]] = {}
    for package_cell, owners_cell in _table_rows(
        text, _RESTRICTED_EXTERNAL_HEADER, 2, "restricted-external"
    ):
        package = package_cell.strip("`")
        if not _BACKTICKED_ONLY.fullmatch(package_cell) or not _TOP_LEVEL_PACKAGE.fullmatch(
            package
        ):
            raise ValueError(
                "§7 restricted-external table: the package cell must hold exactly one "
                f"backticked top-level import name and nothing else, got {package_cell!r}"
            )
        if package == FIRST_PARTY_NAMESPACE:
            raise ValueError(
                f"§7 restricted-external table: {package!r} is the first-party namespace, "
                "not an external package"
            )
        if package in declared:
            raise ValueError(
                f"§7 restricted-external table declares {package!r} more than once; a second "
                "row would replace the first before parity compares it"
            )
        if owners_cell in ("", _NO_GRANTS):
            raise ValueError(
                f"§7 restricted-external table row for {package!r}: the owners cell grants "
                f"no enforcement scope: {owners_cell!r}"
            )
        owners = _backticked_list(owners_cell, "restricted-external", "owners")
        for owner in owners:
            if owner not in owners_universe:
                raise ValueError(
                    f"§7 restricted-external table row for {package!r} grants {owner!r}, "
                    f"which is neither a declared production scope nor {CONFORMANCE_ROOT!r}"
                )
        declared[package] = frozenset(owners)
    return declared


def _compare_declarations(
    left_name: str,
    left: Mapping[str, frozenset[str]],
    right_name: str,
    right: Mapping[str, frozenset[str]],
    subject: str,
    kind: str,
) -> None:
    """Fail when two declarations of one key-to-grants relation disagree."""
    left_only = sorted(set(left) - set(right))
    right_only = sorted(set(right) - set(left))
    if left_only or right_only:
        raise ValueError(
            f"{subject}: declared only in {left_name} {left_only}, "
            f"declared only in {right_name} {right_only}"
        )
    for key in sorted(left):
        if left[key] != right[key]:
            raise ValueError(
                f"{kind} {key!r} has drifted between {left_name} and "
                f"{right_name}: {left_name} grants {sorted(left[key])}, "
                f"{right_name} grants {sorted(right[key])}"
            )


def declared_behavioral_scopes() -> dict[str, str]:
    """The tool's one declaration of §7's behavioral mapping: :data:`MODULE_SCOPE`
    with :data:`PYTEST_BOUNDED_SCOPES` beside it.

    A module named by both would be two declarations of one row — a contract
    source and a pytest boundary — and a merge would keep whichever came last,
    so parity could pass on the spelling the spec carries while ``generate()``
    sourced a contract from the other. Such a module is refused instead.
    """
    both = sorted(set(MODULE_SCOPE) & set(PYTEST_BOUNDED_SCOPES))
    if both:
        raise ValueError(
            f"MODULE_SCOPE and PYTEST_BOUNDED_SCOPES both declare {both}; a behavioral "
            "module is a contract source or a pytest boundary, not both"
        )
    return {**MODULE_SCOPE, **PYTEST_BOUNDED_SCOPES}


def check_behavioral_scope_parity(declared: Mapping[str, str]) -> None:
    """Fail when §7's behavioral-scope table and the tool's declaration of the
    mapping — :func:`declared_behavioral_scopes` — disagree, spec-relative,
    because the spec is authoritative.

    The pytest-bounded rows source no contract, which is why
    :data:`MODULE_SCOPE` omits them; they are compared all the same, so the
    table can neither drop a row the core template requires nor remap one of
    those modules into the package tree while the tool still declares it a
    pytest boundary. Every other row must map its module to the scope the tool
    maps it to, or the generated contracts would be sourced from a scope §7 no
    longer names.
    """
    expected = declared_behavioral_scopes()
    spec_only = sorted(set(declared) - set(expected))
    tool_only = sorted(set(expected) - set(declared))
    if spec_only or tool_only:
        raise ValueError(
            "MODULE_SCOPE has drifted from the spec/python.md §7 behavioral-scope table: "
            f"declared only in the spec {spec_only}, declared only in the tool {tool_only}"
        )
    for module in sorted(declared):
        if declared[module] != expected[module]:
            raise ValueError(
                f"behavioral module {module!r} has drifted between the spec and the tool: "
                f"the spec maps it to {declared[module]!r}, the tool maps it to "
                f"{expected[module]!r}"
            )


def check_first_party_support_parity(declared: Mapping[str, frozenset[str]]) -> None:
    """Fail when §7's first-party support table and
    :data:`PYTHON_FIRST_PARTY_GRANTS` disagree, spec-relative, because the spec
    is authoritative.

    A one-sided edit — a scope or a grant added to the table alone, or to the
    tool alone — fails here before anything is rendered, so ``--write`` cannot
    regenerate a contract the spec does not state.
    """
    _compare_declarations(
        "the spec",
        declared,
        "the tool",
        PYTHON_FIRST_PARTY_GRANTS,
        "PYTHON_FIRST_PARTY_GRANTS has drifted from the spec/python.md §7 first-party "
        "support table",
        kind="first-party support scope",
    )


def check_restricted_external_parity(declared: Mapping[str, frozenset[str]]) -> None:
    """Fail when §7's restricted-external table and :data:`RESTRICTED_EXTERNAL_GRANTS`
    disagree, spec-relative, because the spec is authoritative.

    A one-sided edit — a package or an owner added to the table alone, or to the
    tool alone — fails here before anything is rendered, so ``--write`` cannot
    regenerate a contract the spec does not state.
    """
    _compare_declarations(
        "the spec",
        declared,
        "the tool",
        RESTRICTED_EXTERNAL_GRANTS,
        "RESTRICTED_EXTERNAL_GRANTS has drifted from the spec/python.md §7 "
        "restricted-external table",
        kind="restricted external package",
    )


def check_child_scope_parity(declared: Mapping[str, ChildScope]) -> None:
    """Fail when §7's child-scope table and :data:`CHILD_SCOPES` disagree,
    spec-relative, because the spec is authoritative.

    Sealing generates nothing — ``tools/check_scope_ownership.py`` reading the
    policy is the whole of it — so without this comparison the spec could call a
    scope sealed while the tool no longer sealed it: every contract still
    generated, every check still green, and one declaration still promising a
    guarantee nothing graded. Dropping isolation does move the generated rows,
    so the default check already fails on it; this comparison is what makes
    that failure name the disagreement with §7 rather than report unexplained
    contract drift. The parent is compared with the policy because §7 states
    each policy's guarantee against the parent the row names, and the ownership
    walk takes that parent from the tool's table rather than from §7.
    """
    spec_only = sorted(set(declared) - set(CHILD_SCOPES))
    tool_only = sorted(set(CHILD_SCOPES) - set(declared))
    if spec_only or tool_only:
        raise ValueError(
            "CHILD_SCOPES has drifted from the spec/python.md §7 child-scope table: "
            f"declared only in the spec {spec_only}, declared only in the tool {tool_only}"
        )
    for child in sorted(declared):
        if declared[child] != CHILD_SCOPES[child]:
            raise ValueError(
                f"child scope {child!r} has drifted between the spec and the tool: the "
                f"spec declares {_describe(declared[child])}, the tool declares "
                f"{_describe(CHILD_SCOPES[child])}"
            )


def _describe(child: ChildScope) -> str:
    article = "an" if child.policy == "ordinary" else "a"
    return f"{article} {child.policy} child of {child.parent!r}"


def scope_ancestors(scope: str) -> frozenset[str]:
    """Every declared scope that contains ``scope``, following the child chain."""
    seen: set[str] = set()
    current = CHILD_SCOPES.get(scope)
    while current is not None and current.parent not in seen:
        seen.add(current.parent)
        current = CHILD_SCOPES.get(current.parent)
    return frozenset(seen)


def scope_descendants(scope: str) -> frozenset[str]:
    """Every declared scope nested inside ``scope``, at any depth."""
    return frozenset(child for child in CHILD_SCOPES if scope in scope_ancestors(child))


def scope_siblings(scope: str) -> frozenset[str]:
    """Every other declared child scope sharing ``scope``'s immediate parent.

    A sibling neither contains ``scope`` nor is contained by it, so — unlike the
    shared parent package — it is a forbiddable target in ``scope``'s own row.
    """
    declared = CHILD_SCOPES.get(scope)
    if declared is None:
        return frozenset()
    return frozenset(
        sibling
        for sibling, sibling_declared in CHILD_SCOPES.items()
        if sibling_declared.parent == declared.parent and sibling != scope
    )


def child_grant_exceptions(adjacency: Mapping[str, frozenset[str]], scope: str) -> list[str]:
    """``ignore_imports`` entries for grants a declared descendant holds alone.

    A ``forbidden`` contract's source is package-scoped, so ``scope``'s row also
    governs every module beneath it. A descendant granted a scope its ancestor
    is not — ``parallax.descriptor._hub``'s Hub-construction seam is the only
    such asymmetric grant — would therefore break the ancestor's row. Naming
    that one edge as an exception keeps the row tight for every other module in
    the subtree, which relaxing the row itself would not: import-linter reports
    indirect chains, so ignoring the first hop also withdraws every chain that
    reaches further through it, and only the descendant's *direct* extra grants
    need naming.

    A grant naming a CHILD scope is covered when the ancestor containing it is
    reachable, or IS ``scope`` itself: the ancestor's package covers the child,
    so that grant adds nothing the subtree could not already import and needs no
    exception. The second case is a child granted one of its own siblings — a row
    can neither forbid nor except what sits inside its own source package, and
    whatever the sibling reaches further is already reported from the sibling.

    Two expressions per grant — the granted scope's own interface module and
    ``grant.**`` — because the grant is scope-wide while which spelling the
    descendant reaches it by is not derivable here: a child composing an
    adapter's public value imports the package interface, while one reaching a
    seam inside another scope imports a module beneath it. Only one of the pair
    can match, so the contracts carrying these relax
    ``unmatched_ignore_imports_alerting``; what keeps an exception from
    outliving the import it describes is that it is generated from the §7 grant
    rather than written down, so withdrawing the grant withdraws it.
    """
    reachable = transitive_closure(adjacency, scope)
    return sorted(
        expression
        for child in scope_descendants(scope)
        for grant in adjacency.get(child, frozenset())
        if grant not in reachable and not (scope_ancestors(grant) & (reachable | {scope}))
        for expression in (f"{child} -> {grant}", f"{child} -> {grant}.**")
    )


def minimal_scope_roots(scopes: Iterable[str]) -> tuple[str, ...]:
    """``scopes`` with every member that a member's package already covers dropped.

    A ``forbidden`` contract source is package-scoped, so a scope beneath another
    source adds nothing the ancestor's entry does not already govern.
    """
    members = frozenset(scopes)
    return tuple(scope for scope in sorted(members) if not (scope_ancestors(scope) & members))


def external_contract_sources(
    granted_scopes: AbstractSet[str], production: AbstractSet[str]
) -> tuple[str, ...]:
    """The minimal blocked roots for one restricted external: every production
    scope not granted it, less those a blocked ancestor's package covers.

    A blocked child of a GRANTED parent stays: its parent's package does not
    cover it as a source, and the child's own row is what keeps the grant from
    flowing down.
    """
    return minimal_scope_roots(production - granted_scopes)


def external_child_grant_exceptions(
    *,
    sources: Iterable[str],
    external: str,
    granted_scopes: AbstractSet[str],
) -> tuple[str, ...]:
    """``ignore_imports`` expressions delegating ``external`` to each granted child
    a blocked source's package covers.

    Two expressions per child — the module itself and ``child.**`` — cover a
    module-shaped child and a package-shaped one alike, together with any
    undeclared module beneath it, without scanning source to learn which shape it
    has. That second expression is also why the child must be a leaf of the child
    topology: a declared scope nested beneath it could carry its own policy, and
    import-linter has no expression for "this package and its undeclared
    descendants, excluding declared child packages", so generation fails rather
    than widening the grant.
    """
    delegated = {
        child
        for source in sources
        for child in scope_descendants(source)
        if child in granted_scopes
    }
    non_leaf = sorted(child for child in delegated if scope_descendants(child))
    if non_leaf:
        raise ValueError(
            f"restricted external {external!r} is granted beneath a blocked ancestor to "
            f"child scopes that are not leaves of the child topology: {non_leaf}"
        )
    return tuple(
        expression
        for child in sorted(delegated)
        for expression in (f"{child} -> {external}", f"{child}.** -> {external}")
    )


def unowned_production_interfaces(
    production: AbstractSet[str], roots: Iterable[str]
) -> frozenset[str]:
    """The import-linter roots outside the conformance tree that no production
    scope owns: package interfaces whose one module every package-scoped contract
    misses, and so the exact-module sources of their own external contract."""
    return frozenset(roots) - {CONFORMANCE_ROOT} - production


def build_adjacency(edges: Iterable[tuple[str, str]]) -> dict[str, frozenset[str]]:
    """Map every scope to the set of scopes it may *directly* depend on.

    Fails loudly rather than silently dropping a dependency: if a mapped module
    (one in ``MODULE_SCOPE``) depends on a core-DAG module that ``MODULE_SCOPE``
    does not model, the §7 enforcement map is stale and generation aborts. Edges
    whose *importer* is unmapped (a deferred / out-of-slice module the Python
    target does not enforce) are skipped. First-party grant targets are likewise
    checked against the known scope set.
    """
    nodes = declared_first_party_scopes()
    for scope, deps in PYTHON_FIRST_PARTY_GRANTS.items():
        unknown = deps - nodes
        if unknown:
            raise ValueError(
                f"first-party support scope {scope!r} depends on scopes absent from the "
                f"§7 enforcement map: {sorted(unknown)}"
            )
    direct: dict[str, set[str]] = {node: set() for node in nodes}
    for importer, imported in edges:
        if importer not in MODULE_SCOPE:
            continue
        if imported not in MODULE_SCOPE:
            raise ValueError(
                f"mapped module {importer!r} depends on {imported!r}, which "
                "MODULE_SCOPE does not model — the §7 enforcement map is stale"
            )
        direct[MODULE_SCOPE[importer]].add(MODULE_SCOPE[imported])
    for scope, deps in PYTHON_FIRST_PARTY_GRANTS.items():
        direct[scope].update(deps)
    return {node: frozenset(deps) for node, deps in direct.items()}


def transitive_closure(adjacency: Mapping[str, frozenset[str]], start: str) -> frozenset[str]:
    """All scopes reachable from ``start`` following permitted dependency edges."""
    seen: set[str] = set()
    queue: deque[str] = deque(adjacency.get(start, frozenset()))
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(adjacency.get(node, frozenset()))
    return frozenset(seen)


def compute_forbidden(adjacency: Mapping[str, frozenset[str]]) -> dict[str, list[str]]:
    """For each production scope (:func:`production_scopes`), the sorted scopes
    it may not import.

    Targets are every *production* scope the scope's transitive closure does not
    reach, plus the whole ``parallax.conformance`` subtree as a single package
    edge — so every production scope is forbidden from importing any conformance
    scope, modelled or not, and no contract is sourced from one.

    Child scopes (:data:`CHILD_SCOPES`) are excluded from the general target
    set. import-linter's ``forbidden`` contracts are package-scoped on
    both sides, so a child named inside its own parent's forbidden row overlaps
    that contract's source package and is silently skipped; and naming a child
    in some *other* scope's row would only restate what the parent's own entry
    already forbids for every descendant. For the same overlap reason a child's
    own row omits its ancestors.

    That restatement argument holds only where the parent is itself forbidden. A
    scope GRANTED the parent reaches every child through the parent's package,
    which is why the ``isolated`` policy names the children no grant on the
    parent carries: each is a target in every row that neither contains it nor is
    contained by it, granted or not, so importing one is a rejected import rather
    than an absent grant.

    A **zero-grant** scope is the one source that also takes its SIBLING child
    scopes as targets (:func:`scope_siblings`). A scope granted nothing may
    import nothing, and the general target set cannot say so: everything left
    inside the shared parent package is unreachable from the row, since the
    package itself is an ancestor and overlaps. A sibling is neither ancestor
    nor descendant, so it does not overlap and import-linter checks the pair.
    That makes importing a DECLARED sibling a gate failure rather than a
    convention; ``tools/check_scope_ownership.py`` covers a shape this row
    cannot reach, refusing a module beside the scope that is import-free and
    covered by no declared child scope.
    Siblings are added only for a zero-grant source:
    a scope with grants has a closure to complement, and widening every child's
    row to name its siblings would forbid intra-package edges §7 permits.

    A row stays tight even where a declared descendant holds a grant the scope
    itself lacks: :func:`child_grant_exceptions` carries that asymmetry as one
    named exception rather than widening what the whole subtree may import.

    Reaching a child scope also omits that child's ancestors, for the same
    package-scoped reason: a forbidden entry naming the ancestor package would
    also forbid the granted child inside it, so the row could not both permit
    the narrow grant and forbid the wide package. Only the ancestor's own NAME
    is given up — whatever the rest of that package reaches stays forbidden, and
    is reported as an indirect chain, which is what lets a narrowed grant put a
    target the wide package reaches back inside this row.
    """
    production = production_scopes()
    production_targets = production - set(CHILD_SCOPES)
    all_targets = production_targets | {CONFORMANCE_ROOT} | scopes_with_policy("isolated")
    forbidden: dict[str, list[str]] = {}
    for scope in sorted(production):
        allowed = transitive_closure(adjacency, scope)
        reached_ancestors = {a for granted in allowed for a in scope_ancestors(granted)}
        targets = all_targets
        if not adjacency[scope]:
            targets = all_targets | scope_siblings(scope)
        blocked = (
            targets
            - allowed
            - {scope}
            - scope_ancestors(scope)
            - scope_descendants(scope)
            - reached_ancestors
        )
        forbidden[scope] = sorted(blocked)
    return forbidden


def _toml_str_list(values: Iterable[str], indent: str = "    ") -> str:
    items = list(values)
    if not items:
        return "[]"
    body = "".join(f'{indent}"{value}",\n' for value in items)
    return f"[\n{body}]"


def _toml_sources(values: Iterable[str]) -> str:
    items = list(values)
    if len(items) == 1:
        return f'["{items[0]}"]'
    return _toml_str_list(items)


def _render_forbidden_contract(
    *,
    name: str,
    sources: Iterable[str],
    forbidden: Iterable[str],
    ignore_imports: Iterable[str] = (),
    unmatched_ignore_imports_alerting: str | None = None,
    allow_indirect_imports: bool = False,
    as_packages: bool = True,
) -> list[str]:
    """One ``forbidden`` contract as TOML lines, in import-linter's field order.

    Formatting only: which sources, targets, exceptions, and flags a contract
    carries is the caller's policy.
    """
    lines = [
        "",
        "[[tool.importlinter.contracts]]",
        f'name = "{name}"',
        'type = "forbidden"',
        f"source_modules = {_toml_sources(sources)}",
    ]
    ignored = list(ignore_imports)
    if ignored:
        lines.append(f"ignore_imports = {_toml_str_list(ignored)}")
    if unmatched_ignore_imports_alerting is not None:
        lines.append(f'unmatched_ignore_imports_alerting = "{unmatched_ignore_imports_alerting}"')
    lines.append(f"forbidden_modules = {_toml_str_list(forbidden)}")
    if not as_packages:
        lines.append("as_packages = false")
    if allow_indirect_imports:
        lines.append("allow_indirect_imports = true")
    return lines


def render_block(
    forbidden: Mapping[str, list[str]],
    exceptions: Mapping[str, list[str]],
) -> str:
    """Render the ``[tool.importlinter]`` section: the roots and the unowned
    package interfaces derived from the declared scopes, one first-party
    contract per production scope, one direct-only contract per restricted
    external, and one exact-module contract over those interfaces, each family
    sorted.

    ``include_external_packages`` is what lets a contract name an external at
    all; grimp then records each imported external as one squashed node and
    reads none of its source, so the option costs the graph only those nodes.
    """
    production = production_scopes()
    roots = root_packages()
    lines: list[str] = [
        f"# Generated by {_TOOL} from core/spec/modules.md and spec/python.md §7"
        " — do not edit by hand.",
        f"# Regenerate with: uv run python {_TOOL} --write",
        "[tool.importlinter]",
        f"root_packages = {_toml_str_list(roots)}",
        "include_external_packages = true",
    ]
    for scope in sorted(forbidden):
        excepted = exceptions.get(scope, [])
        lines.extend(
            _render_forbidden_contract(
                name=f"{scope} may import only its permitted dependencies",
                sources=[scope],
                forbidden=forbidden[scope],
                ignore_imports=excepted,
                unmatched_ignore_imports_alerting="none" if excepted else None,
            )
        )
    for package in sorted(RESTRICTED_EXTERNAL_GRANTS):
        granted = RESTRICTED_EXTERNAL_GRANTS[package]
        sources = external_contract_sources(granted, production)
        delegated = external_child_grant_exceptions(
            sources=sources, external=package, granted_scopes=granted
        )
        lines.extend(
            _render_forbidden_contract(
                name=f"Direct imports of {package} require an explicit §7 grant",
                sources=sources,
                forbidden=[package],
                ignore_imports=delegated,
                unmatched_ignore_imports_alerting="none" if delegated else None,
                allow_indirect_imports=True,
            )
        )
    interfaces = unowned_production_interfaces(production, roots)
    if interfaces:
        lines.extend(
            _render_forbidden_contract(
                name="Unowned production interfaces import no restricted externals directly",
                sources=sorted(interfaces),
                forbidden=sorted(RESTRICTED_EXTERNAL_GRANTS),
                allow_indirect_imports=True,
                as_packages=False,
            )
        )
    return "\n".join(lines)


def splice(current: str, block: str) -> str:
    """Replace the region between the generated markers with ``block``."""
    begin = current.find(_BEGIN)
    end = current.find(_END)
    if begin == -1 or end == -1 or end < begin:
        raise ValueError(f"generated-contract markers not found (or out of order) in {PYPROJECT}")
    before = current[: begin + len(_BEGIN)]
    after = current[end:]
    return f"{before}\n{block}\n{after}"


def generate() -> str:
    python_md = PYTHON_MD.read_text()
    check_behavioral_scope_parity(parse_behavioral_scope_table(python_md))
    check_first_party_support_parity(parse_first_party_support_table(python_md))
    check_restricted_external_parity(parse_restricted_external_table(python_md))
    check_child_scope_parity(parse_child_scope_table(python_md))
    edges = parse_dependency_graph(MODULES_MD.read_text())
    adjacency = build_adjacency(edges)
    forbidden = compute_forbidden(adjacency)
    exceptions = {scope: child_grant_exceptions(adjacency, scope) for scope in forbidden}
    return render_block(forbidden, exceptions)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help="verify the committed contracts match modules.md (default)",
    )
    group.add_argument(
        "--write",
        action="store_true",
        help="regenerate the contracts in pyproject.toml",
    )
    args = parser.parse_args(argv)

    try:
        block = generate()
    except ValueError as error:
        print(f"{_TOOL}: {error}", file=sys.stderr)
        return 1
    current = PYPROJECT.read_text()
    expected = splice(current, block)

    if args.write:
        if expected != current:
            PYPROJECT.write_text(expected)
            print(f"{_TOOL}: wrote regenerated import-linter contracts to {PYPROJECT}")
        else:
            print(f"{_TOOL}: import-linter contracts already up to date")
        return 0

    if expected != current:
        print(
            f"{_TOOL}: import-linter contracts are out of sync with core/spec/modules.md"
            " and spec/python.md §7.\n"
            f"  Run `uv run python {_TOOL} --write` and commit the result.",
            file=sys.stderr,
        )
        return 1
    print(
        f"{_TOOL}: import-linter contracts are in sync with core/spec/modules.md"
        " and spec/python.md §7"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
