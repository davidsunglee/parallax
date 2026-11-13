"""Binding changes released through publication, against real Postgres.

A Serving Model publishes a candidate prepared under a changed binding exactly as
it publishes an edition: the deployment provisions what the candidate places,
the application publishes, and each execution keeps the selection it adopted.
Nothing checks the schema at publication, and a candidate that moves a
surviving table or sequence is refused; moving one is a coordinated migration
behind a replacement root, whose derived names the deployment reconciles when a
physical local name changes.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from contextlib import closing
from typing import Any, Final

import pytest

from parallax.conformance.boundary_runner import fault_injecting_adapter
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import (
    POSTGRES,
    PUBLICATION_RELOCATION_REFUSED,
    Attr,
    BindingError,
    DatabaseError,
    DomainModel,
    Entity,
    ModelSelection,
    PublicationConflictError,
    ServingModel,
    TxTemporal,
    UsageError,
    attr,
    prepare_model,
)
from parallax.core.internal.database_binding import ResolvedBinding
from parallax.core.internal.entity import model_of
from parallax.core.internal.metamodel import EntityIdentity
from parallax.evolution import (
    CoordinatedEvolution,
    UnilateralEvolution,
    evolve,
    schema_delta,
)
from parallax.evolution.operations import TableRelocated
from parallax.postgres import PostgresBinding, PostgresLocation, PostgresTable
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.errors import raises_code
from tests._support.root_ownership import own_root

_SHOP: Final = "release.shop"
_AUDIT: Final = "release.shop.audit"
_BILLING: Final = "release.shop.billing"


class Invoice(Entity, table="mpb_invoice", namespace=_SHOP):
    id: Attr[int] = attr(primary_key=True)
    total: Attr[int]


class Refund(Entity, table="mpb_refund", namespace=_SHOP):
    id: Attr[int] = attr(primary_key=True)
    invoice_id: Attr[int]


class Entry(Entity, table="mpb_entry", namespace=_AUDIT):
    id: Attr[int] = attr(primary_key=True)
    note: Attr[str] = attr(max_length=32)


class Credit(Entity, table="mpb_credit", namespace=_SHOP):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


class Charge(Entity, table="mpb_charge", namespace=_BILLING):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


_R1: Final = DomainModel(Invoice, Refund, Entry)
_R2: Final = DomainModel(Invoice, Refund, Entry, Credit, Charge)
"""Release 2 adds Credit under the default and Charge, the first Entity of `billing`."""
_R3: Final = DomainModel(Invoice, Entry)
"""Release 3 removes Refund, the one Entity its binding maps explicitly."""

_NOT_IN_THE_MODEL: Final = "write-instruction-invalid"
"""A write naming an Entity the adopted selection's model does not declare."""

_PX: Final = PostgresLocation(schema="px")
_AUDIT_SCHEMA: Final = PostgresLocation(schema="px_audit")
_REFUNDS: Final = PostgresTable(schema="px_refunds")
_B1: Final = PostgresBinding(
    default=_PX, namespaces={_AUDIT: _AUDIT_SCHEMA}, entities={f"{_SHOP}.Refund": _REFUNDS}
)
_B2: Final = PostgresBinding(
    default=_PX,
    namespaces={_AUDIT: _AUDIT_SCHEMA, _BILLING: PostgresLocation(schema="px_billing")},
    entities={f"{_SHOP}.Refund": _REFUNDS},
)
"""Binding 2 ships the `billing` namespace key with that namespace's first Entity."""
_B3: Final = PostgresBinding(default=_PX, namespaces={_AUDIT: _AUDIT_SCHEMA})


def _prepared(model: DomainModel, binding: PostgresBinding, edition: str) -> ModelSelection:
    return prepare_model(model, binding=binding, edition=edition)


def _provisioned(
    profile_run: Any,
    model: DomainModel,
    binding: PostgresBinding,
    *,
    later: tuple[DomainModel, PostgresBinding] | None = None,
) -> None:
    """Provision ``model`` under ``binding``. With ``later``, every schema the later
    release places a table in exists first, empty and ungranted, as the deployment
    that owns schemas would have created it; the provider then owns and drops them."""
    if later is not None:
        profile_run.reset(model_of(later[0]), {}, later[1])
    profile_run.reset(model_of(model), {}, binding)


def _deploy(profile_run: Any, statements: Iterable[str], schemas: Iterable[str]) -> None:
    """The deployment's part: run the release's statements, then grant the
    service's role what it needs in every schema the release places tables in."""
    role = POSTGRES.quote(profile_run.default_role.name)
    with closing(profile_run.control()) as control:
        for statement in statements:
            control.execute_write(statement, [])
        for schema in schemas:
            quoted = POSTGRES.quote(schema)
            control.execute_write(f"grant usage on schema {quoted} to {role}", [])
            control.execute_write(
                f"grant select, insert, update, delete on all tables in schema {quoted} to {role}",
                [],
            )


def _rows(profile_run: Any, sql: str) -> list[tuple[object, ...]]:
    with closing(profile_run.control()) as control:
        return [tuple(row) for row in control.execute(sql, [])]


def _serving(profile_run: Any, serving: ServingModel, **options: Any) -> ScopedDatabase:
    return own_root(connect(profile_run.port, serving, **options)).using_database_login()


def _growth_statements() -> tuple[str, ...]:
    evolution = evolve(_R1, _R2, earlier_binding=_B1, later_binding=_B2)
    assert isinstance(evolution, UnilateralEvolution)
    return schema_delta(evolution).statements


# --------------------------------------------------------------------------- #
# Growth publishes hot: migrate, publish, and let each execution adopt.        #
# --------------------------------------------------------------------------- #


def test_binding_growth_publishes_once_migrated_and_every_root_sharing_the_holder_adopts_it(
    profile_run: Any,
) -> None:
    _provisioned(profile_run, _R1, _B1, later=(_R2, _B2))
    r1 = _prepared(_R1, _B1, "r1")
    serving = ServingModel(r1)
    first, second = _serving(profile_run, serving), _serving(profile_run, serving)
    first.transact(lambda tx: tx.insert(Invoice(id=1, total=100)))

    assert _growth_statements() == (
        "create table px_billing.mpb_charge (id bigint not null, amount bigint not null, "
        "primary key (id))",
        "create table px.mpb_credit (id bigint not null, amount bigint not null, primary key (id))",
    )
    _deploy(profile_run, _growth_statements(), ("px", "px_billing"))
    r2 = _prepared(_R2, _B2, "r2")

    def publish_mid_transaction(tx: TxnContext) -> str:
        serving.publish(r2, expected=r1)
        with raises_code(UsageError, _NOT_IN_THE_MODEL, match="billing.Charge"):
            tx.wire.insert(f"{_BILLING}.Charge", {"id": 1, "amount": 5})
        tx.insert(Invoice(id=2, total=200))
        return tx.edition

    assert first.transact(publish_mid_transaction) == "r1"
    first.transact(lambda tx: tx.insert(Charge(id=1, amount=5)))
    second.transact(lambda tx: tx.wire.insert(f"{_SHOP}.Credit", {"id": 1, "amount": 7}))

    assert second.transact(lambda tx: tx.edition) == "r2"
    assert [invoice.id for invoice in second.find(Invoice.where(Invoice.id > 0)).results()] == [
        1,
        2,
    ]
    assert _rows(profile_run, "select id, amount from px_billing.mpb_charge") == [(1, 5)]
    assert _rows(profile_run, "select id, amount from px.mpb_credit") == [(1, 7)]


def test_a_retry_after_a_binding_publication_adopts_the_candidate_and_writes_its_new_table(
    profile_run: Any,
) -> None:
    _provisioned(profile_run, _R1, _B1, later=(_R2, _B2))
    _deploy(profile_run, _growth_statements(), ("px", "px_billing"))
    r1, r2 = _prepared(_R1, _B1, "r1"), _prepared(_R2, _B2, "r2")
    serving = ServingModel(r1)
    port = fault_injecting_adapter(profile_run.port, fault="deadlock", persistent=False)
    db = own_root(connect(port, serving)).using_database_login()
    seen: list[str] = []

    def body(tx: TxnContext) -> None:
        seen.append(tx.edition)
        if tx.edition == "r1":
            serving.publish(r2, expected=r1)
        else:
            tx.insert(Charge(id=1, amount=5))
        tx.insert(Invoice(id=len(seen), total=100))

    # The first attempt's write meets the injected deadlock; the retry adopts
    # what is held by then, under which Charge has a table.
    db.transact(body)
    assert seen == ["r1", "r2"]
    assert _rows(profile_run, "select id from px_billing.mpb_charge") == [(1,)]
    assert _rows(profile_run, "select id from px.mpb_invoice") == [(2,)]


def test_publication_checks_no_schema_so_the_first_write_finds_the_missing_table(
    profile_run: Any,
) -> None:
    _provisioned(profile_run, _R1, _B1, later=(_R2, _B2))
    _deploy(profile_run, (), ("px_billing",))
    r1, r2 = _prepared(_R1, _B1, "r1"), _prepared(_R2, _B2, "r2")
    serving = ServingModel(r1)
    db = _serving(profile_run, serving)

    # Publishing before the migration is the application's mistake, and nothing
    # catches it until a statement reaches the table that isn't there.
    serving.publish(r2, expected=r1)
    with pytest.raises(DatabaseError) as missing:
        db.transact(lambda tx: tx.insert(Charge(id=1, amount=5)))
    assert missing.value.native_code == "42P01"

    _deploy(profile_run, _growth_statements(), ("px", "px_billing"))
    db.transact(lambda tx: tx.insert(Charge(id=1, amount=5)))
    assert _rows(profile_run, "select id from px_billing.mpb_charge") == [(1,)]


# --------------------------------------------------------------------------- #
# Removal publishes with its binding entries; adopted work keeps its mapping.  #
# --------------------------------------------------------------------------- #


def test_removing_an_owner_needs_its_entry_removed_and_publishes_hot() -> None:
    with pytest.raises(BindingError) as stale:
        _prepared(_R3, _B1, "r3")
    assert [issue.code for issue in stale.value.issues] == ["binding-entity-unknown"]

    r1, r3 = _prepared(_R1, _B1, "r1"), _prepared(_R3, _B3, "r3")
    serving = ServingModel(r1)
    serving.publish(r3, expected=r1)
    assert serving.current() is r3


def test_a_transaction_and_a_stream_keep_the_mapping_they_adopted_across_a_removal(
    profile_run: Any,
) -> None:
    _provisioned(profile_run, _R1, _B1)
    r1, r3 = _prepared(_R1, _B1, "r1"), _prepared(_R3, _B3, "r3")
    serving = ServingModel(r1)
    db = _serving(profile_run, serving)
    db.transact(lambda tx: [tx.insert(Refund(id=key, invoice_id=1)) for key in (1, 2, 3)])
    streamed: list[int] = []

    with db.stream(Refund.where(Refund.id > 0), batch_size=1) as stream:
        for refund in stream:
            streamed.append(refund.id)
            if refund.id == 1:

                def publish_then_write(tx: TxnContext) -> str:
                    serving.publish(r3, expected=r1)
                    tx.insert(Refund(id=4, invoice_id=1))
                    return tx.edition

                # This transaction opened under r1, so it still writes Refund
                # where r1's binding placed it after r3 is published.
                assert db.transact(publish_then_write) == "r1"
            assert stream.edition == "r1"

    # Every later page still reads the table r1 placed, and finds the row the
    # r1 transaction committed there after the publication.
    assert streamed == [1, 2, 3, 4]
    assert _rows(profile_run, "select id from px_refunds.mpb_refund order by id") == [
        (1,),
        (2,),
        (3,),
        (4,),
    ]
    with raises_code(UsageError, _NOT_IN_THE_MODEL, match="shop.Refund"):
        db.transact(lambda tx: tx.wire.insert(f"{_SHOP}.Refund", {"id": 5, "invoiceId": 1}))
    assert db.transact(lambda tx: tx.edition) == "r3"


# --------------------------------------------------------------------------- #
# Concurrent publishers: the loser rebases and is judged against the winner.   #
# --------------------------------------------------------------------------- #


def test_a_stale_binding_publisher_is_refused_and_its_rebase_is_judged_against_the_winner() -> None:
    r1 = _prepared(_R1, _B1, "r1")
    winner = _prepared(_R2, _B2, "r2-a")
    loser_binding = PostgresBinding(
        default=PostgresLocation(schema="px_next"),
        namespaces=_B2.namespaces,
        entities={f"{_SHOP}.Refund": _REFUNDS, f"{_SHOP}.Invoice": PostgresTable(schema="px")},
    )
    loser = _prepared(_R2, loser_binding, "r2-b")
    serving = ServingModel(r1)
    serving.publish(winner, expected=r1)

    with pytest.raises(PublicationConflictError) as stale:
        serving.publish(loser, expected=r1)
    assert stale.value.held is winner

    # Against r1 the loser moves nothing, because r1 has no Credit; against the
    # winner it moves the Credit table the winner placed in `px`.
    with pytest.raises(UsageError) as refused:
        serving.publish(loser, expected=stale.value.held)
    assert refused.value.code == PUBLICATION_RELOCATION_REFUSED
    assert f"{_SHOP}.Credit from px.mpb_credit to px_next.mpb_credit" in str(refused.value)
    assert serving.current() is winner


# --------------------------------------------------------------------------- #
# Declared table renames: masked ones publish, unmasked ones relocate.         #
# --------------------------------------------------------------------------- #


class Vault(TxTemporal, table="mpb_vault", namespace=_SHOP):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


def _renamed_vault(table: str) -> Any:
    """A Vault class equal to :class:`Vault` but for its declared table."""
    return type(
        "Vault",
        (TxTemporal,),
        {
            "__module__": __name__,
            "__annotations__": {"id": Attr[int], "label": Attr[str]},
            "id": attr(primary_key=True),
            "label": attr(max_length=16),
        },
        table=table,
        namespace=_SHOP,
    )


_ARCHIVED_VAULT: Final[Any] = _renamed_vault("mpb_vault_archive")
_VAULTS: Final = DomainModel(Vault)
_ARCHIVED: Final = DomainModel(_ARCHIVED_VAULT)
_VAULT: Final = EntityIdentity(_SHOP, "Vault")
_VAULT_KEY: Final = f"{_SHOP}.Vault"
_DEFAULT: Final = PostgresBinding(default=_PX)
_MASKING: Final = PostgresBinding(
    default=_PX, entities={_VAULT_KEY: PostgresTable(name="mpb_vault")}
)
"""The binding pinning the physical local name the declared rename would change."""
_JAN, _MAR, _MAY, _JUN = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 5, 6))


def test_an_unmasked_declared_rename_relocates_and_publication_refuses_it() -> None:
    r1 = _prepared(_VAULTS, _DEFAULT, "r1")
    with pytest.raises(UsageError) as refused:
        ServingModel(r1).publish(_prepared(_ARCHIVED, _DEFAULT, "r2"), expected=r1)
    assert refused.value.code == PUBLICATION_RELOCATION_REFUSED
    assert f"{_VAULT_KEY} from px.mpb_vault to px.mpb_vault_archive" in str(refused.value)


def _seed_a_terminated_vault(profile_run: Any, serving: ServingModel) -> None:
    """The vault was known from January until its termination in May."""
    _serving(profile_run, serving, clock=ScriptedClock([_JAN])).transact(
        lambda tx: tx.insert(Vault(id=1, label="seeded"))
    )
    _serving(profile_run, serving, clock=ScriptedClock([_MAY])).transact(
        lambda tx: tx.terminate(tx.find(Vault.where(Vault.id == 1)).result())
    )


def _reopen(db: ScopedDatabase, attempts: list[None]) -> None:
    def reopen(tx: TxnContext) -> None:
        attempts.append(None)
        tx.wire.insert(_VAULT_KEY, {"id": 1, "label": "again"})

    db.transact(reopen)


def _vault_history(profile_run: Any, table: str) -> list[tuple[object, ...]]:
    return _rows(
        profile_run,
        "select in_z, case when out_z = 'infinity' then null else out_z end, label "
        f"from {table} order by in_z",
    )


def test_a_masked_declared_rename_publishes_and_its_temporal_conflicts_stay_recognized(
    profile_run: Any,
) -> None:
    _provisioned(profile_run, _VAULTS, _DEFAULT)
    r1 = _prepared(_VAULTS, _DEFAULT, "r1")
    serving = ServingModel(r1)
    _seed_a_terminated_vault(profile_run, serving)

    masked = evolve(_VAULTS, _ARCHIVED, earlier_binding=_DEFAULT, later_binding=_MASKING)
    assert isinstance(masked, UnilateralEvolution)
    assert schema_delta(masked).statements == ()
    r2 = _prepared(_ARCHIVED, _MASKING, "r2")
    serving.publish(r2, expected=r1)

    # A clock at March reopens the vault inside its history, which the
    # exclusion refuses; recognized as the statement's own temporal conflict
    # under r2's names, which the masked rename left unchanged, it is retried in
    # June.
    attempts: list[None] = []
    _reopen(_serving(profile_run, serving, clock=ScriptedClock([_MAR, _JUN])), attempts)
    assert len(attempts) == 2
    assert _vault_history(profile_run, "px.mpb_vault") == [
        (_JAN, _MAY, "seeded"),
        (_JUN, None, "again"),
    ]


# --------------------------------------------------------------------------- #
# Relocation: a coordinated migration behind a replacement root.               #
# --------------------------------------------------------------------------- #


def _relocation_refused(earlier: ModelSelection, later: ModelSelection) -> None:
    with pytest.raises(UsageError) as refused:
        ServingModel(earlier).publish(later, expected=earlier)
    assert refused.value.code == PUBLICATION_RELOCATION_REFUSED


def test_a_schema_move_behind_a_replacement_root_keeps_every_derived_name(
    profile_run: Any,
) -> None:
    moved = PostgresBinding(default=_PX, entities={_VAULT_KEY: PostgresTable(schema="px_hist")})
    _provisioned(profile_run, _VAULTS, _DEFAULT, later=(_VAULTS, moved))
    r1 = _prepared(_VAULTS, _DEFAULT, "r1")
    serving = ServingModel(r1)
    _seed_a_terminated_vault(profile_run, serving)

    evolution = evolve(_VAULTS, _VAULTS, earlier_binding=_DEFAULT, later_binding=moved)
    assert isinstance(evolution, CoordinatedEvolution)
    assert [type(operation) for operation in evolution.operations] == [TableRelocated]
    replacement = _prepared(_VAULTS, moved, "r1-moved")
    _relocation_refused(r1, replacement)

    # With the old root drained, the deployment moves the table, which takes its
    # constraints and indexes with it under their names, and serves a
    # replacement root from a Serving Model of its own.
    _deploy(profile_run, ("alter table px.mpb_vault set schema px_hist",), ("px_hist",))
    attempts: list[None] = []
    _reopen(
        _serving(profile_run, ServingModel(replacement), clock=ScriptedClock([_MAR, _JUN])),
        attempts,
    )
    assert len(attempts) == 2
    assert _vault_history(profile_run, "px_hist.mpb_vault") == [
        (_JAN, _MAY, "seeded"),
        (_JUN, None, "again"),
    ]


def test_a_local_name_rename_serves_only_once_its_derived_names_are_reconciled(
    profile_run: Any,
) -> None:
    renamed = PostgresBinding(
        default=_PX, entities={_VAULT_KEY: PostgresTable(name="mpb_vault_live")}
    )
    _provisioned(profile_run, _VAULTS, _DEFAULT)
    r1 = _prepared(_VAULTS, _DEFAULT, "r1")
    _seed_a_terminated_vault(profile_run, ServingModel(r1))
    replacement = _prepared(_VAULTS, renamed, "r1-renamed")
    _relocation_refused(r1, replacement)

    # A bare rename leaves the constraints under the names the old local name
    # derived, so the replacement root does not recognize the exclusion its
    # reopen meets as its own temporal conflict, and does not retry it.
    _deploy(profile_run, ("alter table px.mpb_vault rename to mpb_vault_live",), ())
    db = _serving(profile_run, ServingModel(replacement), clock=ScriptedClock([_MAR, _JUN]))
    attempts: list[None] = []
    with pytest.raises(DatabaseError) as unrecognized:
        _reopen(db, attempts)
    assert (len(attempts), unrecognized.value.native_code) == (1, "23P01")

    _deploy(profile_run, _reconciled_names(_DEFAULT, renamed), ())
    attempts.clear()
    _reopen(
        _serving(profile_run, ServingModel(replacement), clock=ScriptedClock([_MAR, _JUN])),
        attempts,
    )
    assert len(attempts) == 2
    assert _vault_history(profile_run, "px.mpb_vault_live") == [
        (_JAN, _MAY, "seeded"),
        (_JUN, None, "again"),
    ]


def _reconciled_names(earlier: PostgresBinding, later: PostgresBinding) -> list[str]:
    """The deployment's renames of every derived temporal name, from the names the
    earlier local name derived to the ones the later binding's resolution expects."""
    before, after = (
        ResolvedBinding(model_of(_VAULTS), binding).table(_VAULT) for binding in (earlier, later)
    )
    assert before.temporal_constraints is not None
    assert after.temporal_constraints is not None
    pairs = (
        (before.temporal_constraints.primary_key_name, after.temporal_constraints.primary_key_name),
        (
            before.temporal_constraints.transaction_check_name,
            after.temporal_constraints.transaction_check_name,
        ),
        (before.temporal_constraints.exclusion_name, after.temporal_constraints.exclusion_name),
    )
    assert all(old != new for old, new in pairs)
    return [
        f"alter table {after.sql} rename constraint {POSTGRES.quote(old)} to {POSTGRES.quote(new)}"
        for old, new in pairs
    ]
