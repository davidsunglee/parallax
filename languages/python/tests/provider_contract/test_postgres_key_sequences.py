"""Native key reservations against a real server: the shipped adapter's lazy
reservation capacity, the login it reserves under, and the live sequence
definition every reservation checks."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from typing import Any, Final

import pytest

from parallax.core import (
    Attr,
    ConnectionAcquisitionError,
    DomainModel,
    Entity,
    KeySequence,
    UsageError,
    attr,
)
from parallax.core.internal.entity._model import model_of
from parallax.postgres import PoolOptions, PostgresBinding, PostgresLocation, PostgresSequence
from parallax.snapshot import TxnContext, connect
from tests._support.bindings import TEST_BINDING, TEST_SCHEMA
from tests._support.errors import raises_code
from tests._support.root_ownership import own_root


class Voucher(Entity, table="pks_voucher", namespace="key.sequences"):
    id: Attr[int] = attr(primary_key=KeySequence("pks_voucher_ids", batch_size=5))
    label: Attr[str] = attr(max_length=16)


_MODEL: Final = DomainModel(Voucher)
_SEQUENCE: Final = f"{TEST_SCHEMA}.pks_voucher_ids"


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    database_authorization: object


def _keyless(label: str) -> Any:
    def insert(tx: TxnContext) -> object:
        return tx.insert(Voucher(label=label)).id

    return insert


def _sequence_state(profile_run: Any, sequence: str = _SEQUENCE) -> tuple[object, ...]:
    with closing(profile_run.control()) as control:
        ((last, called),) = control.execute(f"select last_value, is_called from {sequence}", [])
    return (last, called)


def _stored(profile_run: Any) -> list[tuple[object, ...]]:
    with closing(profile_run.control()) as control:
        return [
            tuple(row)
            for row in control.execute(
                f"select id, label from {TEST_SCHEMA}.pks_voucher order by id", []
            )
        ]


def test_a_principal_without_sequence_privilege_inserts_through_the_login_s_reservation(
    profile_run: Any,
) -> None:
    # Provisioning grants the conformance roles their tables and the login's own
    # role alone the sequence, as a deployment's application roles hold no
    # privilege on the sequence its service login reserves from.
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    role = profile_run.authorization("role-a")
    with closing(profile_run.control()) as control:
        ((allowed,),) = control.execute(
            "select has_sequence_privilege(?, ?, 'USAGE')", [role.name, _SEQUENCE]
        )
    assert allowed is False
    root = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING))
    db = root.using_principal(_Principal("key-sequences", role))

    assert db.transact(_keyless("first")) == 1
    assert _stored(profile_run) == [(1, "first")]


def test_a_root_whose_only_application_connection_is_held_still_reserves(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    configuration = profile_run.configured(pool=PoolOptions(min_size=1, max_size=1))
    root = own_root(connect(configuration, _MODEL, binding=TEST_BINDING))
    db = root.using_database_login()

    def insert(tx: TxnContext) -> list[int]:
        return [tx.insert(Voucher(label=f"v{index}")).id for index in range(6)]

    assert db.transact(insert) == [1, 2, 3, 4, 5, 6]
    assert _sequence_state(profile_run) == (6, True)


def test_a_root_reserves_nothing_until_a_keyless_insert_and_then_hands_out_locally(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    root = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING))
    db = root.using_database_login()
    db.transact(lambda tx: tx.insert(Voucher(id=100, label="given")))
    assert _sequence_state(profile_run) == (1, False)

    assert [db.transact(_keyless(f"v{index}")) for index in range(5)] == [1, 2, 3, 4, 5]
    # One block of five served all five transactions.
    assert _sequence_state(profile_run) == (1, True)
    assert db.transact(_keyless("next")) == 6
    assert _sequence_state(profile_run) == (6, True)


def test_a_closed_root_refuses_new_work_though_it_still_held_reserved_keys(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    root = connect(profile_run.port, _MODEL, binding=TEST_BINDING)
    db = root.using_database_login()
    assert db.transact(_keyless("first")) == 1
    root.close()

    with pytest.raises(ConnectionAcquisitionError) as refused:
        db.transact(_keyless("after"))
    assert refused.value.reason == "closed"
    # A replacement root abandons what the closed one reserved and never reused.
    replacement = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING))
    assert replacement.using_database_login().transact(_keyless("replaced")) == 6


def test_a_reservation_finding_no_sequence_is_refused_and_keeps_nothing(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    with closing(profile_run.control()) as control:
        control.execute_write(f"drop sequence {_SEQUENCE}", [])
    db = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING)).using_database_login()

    with raises_code(UsageError, "key-sequence-missing"):
        db.transact(_keyless("missing"))
    assert _stored(profile_run) == []


@pytest.mark.parametrize(
    ("alteration", "detail"),
    [
        ("increment by 7", "steps by 7"),
        ("cycle", "cycles"),
    ],
    ids=["increment", "cycling"],
)
def test_a_reservation_under_an_altered_definition_is_refused_and_abandoned(
    profile_run: Any, alteration: str, detail: str
) -> None:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    with closing(profile_run.control()) as control:
        control.execute_write(f"alter sequence {_SEQUENCE} {alteration}", [])
    db = own_root(connect(profile_run.port, _MODEL, binding=TEST_BINDING)).using_database_login()

    with raises_code(UsageError, "key-sequence-mismatch", match=detail):
        db.transact(_keyless("altered"))
    assert _stored(profile_run) == []


_QUALIFIED: Final = PostgresBinding(
    default=PostgresLocation(TEST_SCHEMA),
    sequences={"pks_voucher_ids": PostgresSequence(schema="Key.Ring", name="voucher.ids")},
)


def test_a_misleading_search_path_redirects_neither_ddl_nor_reservation(
    profile_run: Any,
) -> None:
    # The sequence's schema and name each hold a dot and capitals, so only a
    # name quoted component by component reaches it; a same-named decoy first
    # on the search path catches anything resolved without qualification.
    profile_run.reset(model_of(_MODEL), {}, _QUALIFIED)
    role = profile_run.default_role.name
    with closing(profile_run.control()) as control:
        control.execute_write('create sequence public."voucher.ids" increment by 5', [])
        control.execute_write(f'grant usage on sequence public."voucher.ids" to "{role}"', [])
    configuration = profile_run.configured(settings={"search_path": "public"})
    db = own_root(connect(configuration, _MODEL, binding=_QUALIFIED)).using_database_login()

    assert db.transact(_keyless("qualified")) == 1
    assert _sequence_state(profile_run, '"Key.Ring"."voucher.ids"') == (1, True)
    assert _sequence_state(profile_run, 'public."voucher.ids"') == (1, False)
