"""Putting a case's declared starting state into a database.

Three functions composing :func:`~reference_harness.ddl_builder.ddl_for` and
:func:`~reference_harness.data_loader.load_model` — deliberately about as much
interface as implementation. This module is **shallow by design** and exists for
two reasons that have nothing to do with depth: every lane calls ``apply_given``
at the same point, so the timing rule is stated once rather than once per lane;
and the Unit Work Scenario package and :mod:`.case_runner` both need these, while
the runner imports the package, so a home either of them owned would be an import
cycle. Nothing here is a seam — do not hang lane variation off it.
"""

from __future__ import annotations

from ._statement_bind_inference import managed_statement_binds
from .case import Case
from .data_loader import load_model
from .ddl_builder import ddl_for
from .providers import DatabaseProvider

__all__ = ["apply_given", "provision", "provision_empty"]


def provision(case: Case, db: DatabaseProvider) -> None:
    """Put *db* into *case*'s declared starting state, discarding whatever it held.

    Destructive and complete: the database is reset, the model's derived DDL is
    applied to the empty schema, and the model's fixtures are loaded. A lane whose
    case builds its own history from its own ordered DML wants
    :func:`provision_empty` instead.
    """
    db.reset()
    db.apply_ddl(ddl_for(case.model, db.dialect))
    load_model(case.model, db)


def provision_empty(case: Case, db: DatabaseProvider) -> None:
    """Provision DDL only (no fixture load) for a write-sequence case.

    A write-sequence case constructs its entire milestone history from its own
    ordered DML (the `insert` step is part of the sequence), so it starts from an
    empty schema and is fully self-contained — UNLESS it sets ``given.fixtures``
    (the m-detach detached-update merge-back case), in which case the model's fixtures
    are loaded first so the merge-back can mutate a pre-existing persisted row.
    """
    db.reset()
    db.apply_ddl(ddl_for(case.model, db.dialect))
    if case.load_fixtures:
        load_model(case.model, db)


def apply_given(case: Case, db: DatabaseProvider) -> None:
    """Apply a case's out-of-band ``given.apply`` entries verbatim.

    Every lane that admits the key calls this at the same point — after its own
    provisioning and before the lane's first golden statement or step — so the
    timing and the interpretation are one thing rather than one per lane. Each
    entry's ``sql`` is naive, dialect-agnostic text run as authored; ``binds``
    defaults to empty. A case carrying none applies nothing.
    """
    for entry in case.apply:
        statement = entry["sql"]
        binds = list(entry.get("binds", []))
        db.execute(statement, managed_statement_binds(case, statement, binds, db.dialect))
