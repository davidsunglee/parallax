"""Immutable Postgres configuration: the two retention policies and the adapter (Docker-free).

Configuration is the half of the adapter that owns nothing. Constructing it
opens no connection, no pool, and no thread, which is what makes it safe to
build at import time, share between threads, reuse for two handles, and — for a
forking server — build before the fork and open after it. These pins grade that
resource-freedom, the validation that refuses a malformed policy BEFORE anything
is allocated, and the disclosure rule that keeps a connection string out of the
one error a caller is most likely to log.

What they do not grade is any behavior of a pool: nothing here opens one.
"""

from __future__ import annotations

import dataclasses
import threading
from typing import Any, cast

import psycopg
import pytest

from parallax.postgres import OnDemandOptions, PoolOptions, PostgresAdapter

# --------------------------------------------------------------------------- #
# Defaults: a starting point, stated once.                                     #
# --------------------------------------------------------------------------- #


def test_the_retaining_defaults_are_the_documented_starting_point() -> None:
    options = PoolOptions()
    assert (options.min_size, options.max_size) == (1, 10)
    assert (options.acquire_timeout, options.startup_timeout) == (15.0, 30.0)
    assert (options.max_waiting, options.validate_on_checkout) == (0, True)
    assert (options.max_idle, options.max_lifetime) == (600.0, 3600.0)
    assert (options.reconnect_timeout, options.num_workers) == (300.0, 3)


def test_on_demand_exposes_no_setting_for_inventory_it_does_not_keep() -> None:
    # `min_size` and `max_idle` describe retained capacity, so a policy that
    # retains none has no spelling for either rather than a spelling that means
    # nothing.
    options = OnDemandOptions()
    assert (options.max_size, options.acquire_timeout) == (10, 15.0)
    assert not hasattr(options, "min_size")
    assert not hasattr(options, "max_idle")


def test_omitting_the_policy_selects_the_retaining_defaults() -> None:
    assert PostgresAdapter("").pool == PoolOptions()


# --------------------------------------------------------------------------- #
# Validation: refused before anything is allocated.                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field", ["min_size", "max_size", "max_waiting", "num_workers"])
def test_an_integer_control_refuses_a_boolean(field: str) -> None:
    # `bool` is an `int` subclass, so `max_size=True` would otherwise configure a
    # capacity of one.
    with pytest.raises(TypeError, match=field):
        _options(**{field: True})


@pytest.mark.parametrize("field", ["min_size", "max_size", "max_waiting", "num_workers"])
def test_an_integer_control_refuses_an_integral_float(field: str) -> None:
    # Not coerced: `max_size=10.0` and `max_size=10` would be two spellings a
    # reader has to know are the same.
    with pytest.raises(TypeError, match=field):
        _options(**{field: 10.0})


def test_capacity_is_bounded_and_has_no_unlimited_sentinel() -> None:
    with pytest.raises(ValueError, match="max_size"):
        PoolOptions(max_size=0)
    with pytest.raises(ValueError, match="max_size"):
        OnDemandOptions(max_size=0)


def test_a_minimum_runs_from_zero_through_the_maximum() -> None:
    assert PoolOptions(min_size=0).min_size == 0
    assert PoolOptions(min_size=4, max_size=4).min_size == 4
    with pytest.raises(ValueError, match="min_size"):
        PoolOptions(min_size=5, max_size=4)
    with pytest.raises(ValueError, match="min_size"):
        PoolOptions(min_size=-1)


def test_the_waiting_queue_is_nonnegative_and_zero_means_uncounted() -> None:
    assert PoolOptions(max_waiting=0).max_waiting == 0
    with pytest.raises(ValueError, match="max_waiting"):
        PoolOptions(max_waiting=-1)


def test_maintenance_needs_at_least_one_worker() -> None:
    with pytest.raises(ValueError, match="num_workers"):
        PoolOptions(num_workers=0)


def _options(**overrides: object) -> PoolOptions:
    """A retaining policy built from an untyped mapping, as a caller may.

    Validation exists for values the annotations already refuse, so the pins for
    it hand the constructor what a checked call site could not: the point is the
    runtime refusal, not a second copy of the type checker's own verdict.
    """
    return PoolOptions(**cast("Any", overrides))


@pytest.mark.parametrize(
    "field", ["acquire_timeout", "startup_timeout", "max_idle", "max_lifetime", "reconnect_timeout"]
)
def test_a_duration_takes_finite_positive_seconds(field: str) -> None:
    # Zero and infinity would be sentinels for "disabled" and "unlimited", and
    # neither is a control this configuration offers.
    assert getattr(_options(**{field: 5}), field) == 5.0
    for refused in (True, "5"):
        with pytest.raises(TypeError, match=field):
            _options(**{field: refused})
    for outside in (0, -1.0, float("inf")):
        with pytest.raises(ValueError, match=field):
            _options(**{field: outside})


def test_on_demand_validates_the_controls_it_keeps() -> None:
    assert OnDemandOptions(max_lifetime=60).max_lifetime == 60.0
    with pytest.raises(ValueError, match="reconnect_timeout"):
        OnDemandOptions(reconnect_timeout=0)
    with pytest.raises(TypeError, match="num_workers"):
        OnDemandOptions(num_workers=cast("Any", True))
    with pytest.raises(TypeError, match="validate_on_checkout"):
        OnDemandOptions(validate_on_checkout=cast("Any", 1))


def test_checkout_validation_takes_a_boolean_alone() -> None:
    assert PoolOptions(validate_on_checkout=False).validate_on_checkout is False
    with pytest.raises(TypeError, match="validate_on_checkout"):
        PoolOptions(validate_on_checkout=cast("Any", "yes"))


def test_no_relationship_is_invented_between_independent_controls() -> None:
    # An acquisition budget longer than the startup budget, and an idle
    # retirement longer than a lifetime, are odd rather than invalid: they are
    # separate controls and Parallax states no ordering between them.
    assert PoolOptions(acquire_timeout=60.0, startup_timeout=1.0).acquire_timeout == 60.0
    assert PoolOptions(max_idle=7200.0, max_lifetime=60.0).max_idle == 7200.0


def test_the_policy_itself_is_typed_and_a_bare_flag_is_not_one() -> None:
    with pytest.raises(TypeError, match="PoolOptions or OnDemandOptions"):
        PostgresAdapter("", pool=cast("Any", False))
    with pytest.raises(TypeError, match="PoolOptions or OnDemandOptions"):
        PostgresAdapter("", pool=cast("Any", None))


def test_prepared_statement_tuning_is_a_nonnegative_int_or_none() -> None:
    assert PostgresAdapter("", prepare_threshold=None).prepare_threshold is None
    assert PostgresAdapter("", prepare_threshold=0).prepare_threshold == 0
    with pytest.raises(TypeError, match="prepare_threshold"):
        PostgresAdapter("", prepare_threshold=cast("Any", True))
    with pytest.raises(ValueError, match="prepare_threshold"):
        PostgresAdapter("", prepare_threshold=-1)


# --------------------------------------------------------------------------- #
# Immutability, reuse, and resource-freedom.                                   #
# --------------------------------------------------------------------------- #


def test_configuration_is_frozen_and_changed_by_constructing_another() -> None:
    options = PoolOptions(max_size=20)
    with pytest.raises(dataclasses.FrozenInstanceError):
        options.max_size = 30  # pyright: ignore[reportAttributeAccessIssue]
    # `replace` revalidates rather than bypassing the constructor, so a
    # derived configuration cannot hold a value the original would have refused.
    assert dataclasses.replace(options, max_size=30).max_size == 30
    with pytest.raises(ValueError, match="max_size"):
        dataclasses.replace(options, max_size=0)


def test_an_adapter_is_frozen_and_equal_by_value() -> None:
    adapter = PostgresAdapter("host=localhost dbname=app", pool=PoolOptions(max_size=4))
    with pytest.raises(dataclasses.FrozenInstanceError):
        adapter.connection_string = "host=other"  # pyright: ignore[reportAttributeAccessIssue]
    assert adapter == PostgresAdapter("host=localhost dbname=app", pool=PoolOptions(max_size=4))


def test_a_connection_string_stays_out_of_the_representation() -> None:
    # A connection string is a place a password lives and a repr is a place
    # values get logged.
    adapter = PostgresAdapter("postgresql://user:hunter2@localhost/app")
    assert "hunter2" not in repr(adapter)
    assert adapter.connection_string == "postgresql://user:hunter2@localhost/app"


def test_configuration_reaches_no_driver_and_starts_no_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Constructing is a spelling check and nothing more: no socket, no pool, no
    # maintenance worker — which is what makes building one before a fork safe.
    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("configuration must open no connection")

    monkeypatch.setattr(psycopg, "connect", refuse)
    before = threading.active_count()

    PostgresAdapter("host=localhost dbname=app", pool=OnDemandOptions(max_size=3))

    assert threading.active_count() == before


def test_the_dialect_is_readable_without_configuring_anything() -> None:
    # A composition root selects an adapter and lowers SQL in the spelling it
    # will execute in before any configuration, let alone any resource, exists.
    assert PostgresAdapter.dialect is PostgresAdapter("").dialect


# --------------------------------------------------------------------------- #
# The connection string: libpq's grammar, and a credential-safe refusal.       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "connection_string",
    [
        "host=localhost dbname=app",
        "postgresql://localhost/app",
        "postgresql://user:pw@localhost:5432/app?sslmode=require",
        "service=app",
        "",
    ],
)
def test_every_libpq_form_is_accepted_including_the_empty_string(connection_string: str) -> None:
    # The empty string asks libpq to take everything from the environment, which
    # is a deployment's choice rather than a missing value.
    assert PostgresAdapter(connection_string).connection_string == connection_string


def test_a_non_string_is_refused_by_type() -> None:
    with pytest.raises(TypeError, match=r"connection_string must be a string\."):
        PostgresAdapter(cast("Any", 5432))


def test_malformed_syntax_is_refused_without_quoting_the_input_back() -> None:
    # The refusal is fixed text: a parser's own message can quote the input it
    # rejected, and the input is a connection string.
    with pytest.raises(ValueError) as refused:
        PostgresAdapter("host=localhost dbname")

    assert str(refused.value) == (
        "Invalid PostgreSQL connection string; expected libpq keyword/value syntax "
        "or a PostgreSQL URI."
    )
    assert "dbname" not in str(refused.value)
    # The native parser's own exception is suppressed rather than chained, so it
    # reaches neither the displayed cause chain nor a log that renders one.
    assert refused.value.__cause__ is None
    assert refused.value.__suppress_context__ is True


def test_local_parsing_proves_nothing_about_what_the_string_names() -> None:
    # Environment, service files, credentials and server settings resolve when a
    # physical connection is created, so immutable configuration does not freeze
    # inputs a deployment expects to change underneath it.
    assert PostgresAdapter("host=nowhere.invalid port=1 dbname=absent").connection_string
    assert PostgresAdapter("service=one-that-does-not-exist").connection_string
