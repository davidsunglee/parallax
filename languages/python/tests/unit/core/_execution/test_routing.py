"""Read routing: policy resolution, derivation, and what each operation requests.

Routing outcomes are scripted on the port and the routing RULES are core's: the
policy a root or scope resolves, the one each new execution requests, and the
writer stickiness an operation earns once an acquisition of its own fell back.
Nothing here acquires a connection to decide a policy.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

import pytest

from parallax.core._execution._routing import (
    OperationRouting,
    check_read_policy,
    resolved_read_policy,
)
from parallax.core._execution._scope import ExecutionScope
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    ConnectionAcquisitionError,
    Route,
    RouteCapabilities,
    RoutePolicy,
    RouteSelection,
)
from parallax.core.execution import ExecutionFailure
from parallax.core.execution_lifecycle._activity import ActivityTarget
from tests._support.db_port import ScriptedAdapter, Transact
from tests.unit.core._execution._execution_support import itself, root

_WRITER: Final[Mapping[Route, RouteCapabilities]] = {"writer": RouteCapabilities.every_level()}
_BOTH: Final[Mapping[Route, RouteCapabilities]] = {
    "writer": RouteCapabilities.every_level(),
    "reader": RouteCapabilities.every_level(),
}
_FELL_BACK: Final = RouteSelection("writer", "unavailable")


class _Target:
    @property
    def canonical(self) -> str:
        return "parallax.compatibility.Account"


_TARGET: Final[ActivityTarget] = _Target()


def _read(scope: ExecutionScope) -> None:
    scope.begin().eager(_TARGET, "rows", lambda _activity, _inputs: None)


def _two_pages(scope: ExecutionScope) -> None:
    read = scope.begin()
    with read.open_stream(_TARGET, "rows", 5) as stream:
        read.paged(stream.batch(), lambda _calls, _inputs: None)
        read.paged(stream.batch(), lambda _calls, _inputs: None)


# --------------------------------------------------------------------------- #
# Resolution, without I/O.                                                     #
# --------------------------------------------------------------------------- #


def test_an_omitted_policy_resolves_to_the_declared_topology_s_default() -> None:
    assert resolved_read_policy(None, _WRITER) == "writer_only"
    assert resolved_read_policy(None, _BOTH) == "reader_only"


@pytest.mark.parametrize("policy", ["reader_only", "reader_preferred"])
def test_a_reader_policy_without_a_declared_reader_is_refused(policy: RoutePolicy) -> None:
    with pytest.raises(ValueError) as refused:
        resolved_read_policy(policy, _WRITER)

    assert "with_routing(read_policy='writer_only')" in str(refused.value)
    assert resolved_read_policy(policy, _BOTH) == policy


@pytest.mark.parametrize("value", ["reader", "writer", "READER_ONLY", 1, True])
def test_a_value_outside_the_vocabulary_is_refused_before_any_route_is_consulted(
    value: object,
) -> None:
    with pytest.raises(ValueError, match="read_policy must be one of"):
        check_read_policy(value)


def test_an_unhashable_spelling_is_refused_the_same_way() -> None:
    class _Unhashable(str):
        __hash__ = None  # type: ignore[assignment] - the unhashable spelling is what this proves

    assert check_read_policy(_Unhashable("writer_only")) == "writer_only"
    with pytest.raises(ValueError, match="read_policy must be one of"):
        check_read_policy(_Unhashable("nearest"))


# --------------------------------------------------------------------------- #
# One operation's routing.                                                     #
# --------------------------------------------------------------------------- #


def test_an_operation_requests_its_policy_until_an_acquisition_falls_back() -> None:
    adapter = ScriptedAdapter(routes=("writer", "reader"))
    source = adapter.open().login_source()
    routing = OperationRouting(source, "reader_preferred")

    routing.record(None)
    routing.record(RouteSelection("reader"))
    assert routing.policy == "reader_preferred"

    routing.record(_FELL_BACK)
    routing.record(RouteSelection("writer"))
    assert routing.policy == "writer_only"
    with routing.new_context():
        pass
    assert adapter.requested_policies == ["writer_only"]


# --------------------------------------------------------------------------- #
# Roots and scopes.                                                            #
# --------------------------------------------------------------------------- #


def test_a_single_endpoint_root_reads_and_writes_on_the_writer() -> None:
    adapter = ScriptedAdapter(Transact(), Transact())
    scope = root(adapter).using_database_login()

    _read(scope)
    _two_pages(scope)
    scope.transact(lambda _attempt: None, itself)
    scope.read_only(lambda _attempt: None, itself)

    assert adapter.requested_policies == ["writer_only"] * 5


def test_a_declared_reader_defaults_new_reads_to_it_and_transact_to_the_writer() -> None:
    adapter = ScriptedAdapter(Transact(), Transact(), routes=("writer", "reader"))
    scope = root(adapter).using_database_login()

    _read(scope)
    _two_pages(scope)
    scope.read_only(lambda _attempt: None, itself)
    scope.transact(lambda _attempt: None, itself)

    assert adapter.requested_policies == [
        "reader_only",
        "reader_only",
        "reader_only",
        "reader_only",
        "writer_only",
    ]


@pytest.mark.parametrize("policy", ["reader_only", "reader_preferred"])
def test_explicit_reader_policies_fail_without_any_acquisition(policy: RoutePolicy) -> None:
    adapter = ScriptedAdapter()
    database = root(adapter)
    scope = database.using_database_login()

    with pytest.raises(ValueError, match="needs a reader route"):
        database.with_routing(read_policy=policy)
    with pytest.raises(ValueError, match="needs a reader route"):
        scope.with_routing(read_policy=policy)
    with pytest.raises(ValueError, match="needs a reader route"):
        root(adapter, read_policy=policy)

    assert adapter.acquisitions == 0
    assert adapter.requested_policies == []
    assert adapter.calls == []


def test_routing_derivation_composes_with_authority_and_options_and_acquires_nothing() -> None:
    adapter = ScriptedAdapter(Transact(), routes=("writer", "reader"))
    database = root(adapter)

    pinned = database.with_routing(read_policy="writer_only").with_options(max_retries=2)
    scope = pinned.using_database_login()
    unpinned = scope.with_routing(read_policy="reader_preferred").with_options(
        isolation="serializable"
    )
    assert adapter.acquisitions == 0

    _read(scope)
    _read(unpinned)
    assert scope.read_only(lambda attempt: attempt.options.max_retries, itself) == 2

    assert adapter.requested_policies == ["writer_only", "reader_preferred", "writer_only"]
    shared = cast("Any", unpinned)
    assert shared._authority is cast("Any", scope)._authority
    assert shared._runner is cast("Any", scope)._runner


def test_a_routing_alias_shares_the_root_s_resources_and_close() -> None:
    adapter = ScriptedAdapter(routes=("writer", "reader"))
    database = root(adapter)
    alias = database.with_routing(read_policy="writer_only")

    assert cast("Any", alias)._resources is cast("Any", database)._resources
    alias.close()

    assert adapter.closes == 1
    with pytest.raises(ExecutionFailure) as closed:
        _read(database.using_database_login())
    assert isinstance(closed.value.cause, ConnectionAcquisitionError)
    assert closed.value.cause.reason == "closed"


def test_a_join_never_consults_the_joining_scope_s_routing() -> None:
    adapter = ScriptedAdapter(Transact(), routes=("writer", "reader"))
    database = root(adapter)
    outer = database.using_database_login()
    joining = database.with_routing(read_policy="reader_preferred").using_database_login()

    joined = outer.read_only(
        lambda _attempt: joining.read_only(lambda _joined: "joined", itself), itself
    )

    assert joined == "joined"
    assert adapter.requested_policies == ["reader_only"]


def test_a_standalone_read_inside_a_callback_requests_its_own_scope_s_policy() -> None:
    adapter = ScriptedAdapter(Transact(), routes=("writer", "reader"))
    database = root(adapter)
    writer_scope = database.with_routing(read_policy="writer_only").using_database_login()
    reader_scope = database.using_database_login()

    writer_scope.transact(lambda _attempt: _read(reader_scope), itself)

    assert adapter.requested_policies == ["writer_only", "reader_only"]


# --------------------------------------------------------------------------- #
# Writer stickiness across an operation's acquisitions.                        #
# --------------------------------------------------------------------------- #


def test_a_stream_that_fell_back_keeps_its_later_pages_on_the_writer() -> None:
    adapter = ScriptedAdapter(selections=[_FELL_BACK], routes=("writer", "reader"))
    scope = root(adapter, read_policy="reader_preferred").using_database_login()

    _two_pages(scope)
    _two_pages(scope)

    assert adapter.requested_policies == [
        "reader_preferred",
        "writer_only",
        "reader_preferred",
        "reader_preferred",
    ]


def test_a_read_only_invocation_that_fell_back_retries_on_the_writer() -> None:
    deadlock = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")
    adapter = ScriptedAdapter(
        Transact(commit=deadlock),
        Transact(),
        selections=[_FELL_BACK],
        routes=("writer", "reader"),
    )
    scope = root(adapter, read_policy="reader_preferred").using_database_login()

    scope.read_only(lambda _attempt: None, itself, max_retries=1)

    assert adapter.requested_policies == ["reader_preferred", "writer_only"]


def test_a_failed_acquisition_s_selection_is_recorded_too() -> None:
    refused = ConnectionAcquisitionError("no reader", reason="timeout", selection=_FELL_BACK)
    adapter = ScriptedAdapter(acquisition_failures=[refused], routes=("writer", "reader"))
    scope = root(adapter, read_policy="reader_preferred").using_database_login()
    read = scope.begin()

    with read.open_stream(_TARGET, "rows", 5) as stream:
        with pytest.raises(ConnectionAcquisitionError):
            read.paged(stream.batch(), lambda _calls, _inputs: None)
        read.paged(stream.batch(), lambda _calls, _inputs: None)

    assert adapter.requested_policies == ["reader_preferred", "writer_only"]
