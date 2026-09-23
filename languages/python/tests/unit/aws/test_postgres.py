"""The RDS Postgres factory: configuration, already told what IAM needs. Docker-free.

What is graded is that the adapter it returns is the one an application would
have written by hand — the same destination, the same credential, the same
retention — plus the three facts the factory exists to state once: TLS is not
optional, the token's four bindings are not the caller's to restate, and
everything else about libpq's grammar stays open.

Nothing here reaches AWS or a database: the factory resolves no token and opens
nothing, which is itself one of the assertions below.
"""

from __future__ import annotations

import threading
from functools import partial
from typing import TYPE_CHECKING, cast

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from parallax.aws import RdsIamCredentials
from parallax.aws.postgres import rds_postgres
from parallax.postgres import OnDemandOptions, PoolOptions

if TYPE_CHECKING:
    from botocore.session import Session

    from parallax.postgres import PostgresAdapter

_ENDPOINT = "orders.cluster-abc.us-east-1.rds.amazonaws.com"

_adapter = partial(
    rds_postgres, host=_ENDPOINT, user="orders_service", database="orders", region="us-east-1"
)


def _destination(adapter: PostgresAdapter) -> dict[str, str]:
    return {key: str(value) for key, value in conninfo_to_dict(adapter.connection_string).items()}


def test_the_destination_is_the_endpoint_the_token_is_signed_for_over_tls() -> None:
    # An IAM token is a password, so it travels over TLS; and it proves nothing
    # at a host, port or user other than the ones it was signed for. Stating
    # both once is the whole reason this is a factory. `gssencmode` is part of
    # stating the first: libpq prefers GSS encryption to TLS wherever it is
    # available, whatever `sslmode` asks for, so TLS is required by switching
    # the alternative off as well as by naming it.
    assert _destination(_adapter()) == {
        "host": _ENDPOINT,
        "port": "5432",
        "user": "orders_service",
        "dbname": "orders",
        "sslmode": "require",
        "gssencmode": "disable",
    }


@pytest.mark.parametrize("asked", ["require", "prefer", "allow"])
def test_gss_encryption_in_tls_s_place_is_refused(asked: str) -> None:
    with pytest.raises(ValueError) as refused:
        _adapter(params={"gssencmode": asked, "options": "-c application_name=hunter2"})

    assert str(refused.value) == (
        "params must not enable gssencmode; an IAM token travels only over TLS."
    )
    assert "hunter2" not in str(refused.value)


def test_a_host_naming_more_than_one_endpoint_is_refused() -> None:
    # libpq reads a comma-separated `host` as a list of endpoints to try in
    # turn, while the token would be signed for the literal list: every
    # connection the adapter opened would present a token signed for somewhere
    # else, and no attempt would authenticate.
    with pytest.raises(ValueError) as refused:
        _adapter(host=f"{_ENDPOINT},replica.cluster-abc.us-east-1.rds.amazonaws.com")

    assert str(refused.value) == (
        "host must name one endpoint; a token is signed for the host it names, not for a list."
    )


def test_the_credential_is_bound_to_the_same_endpoint_and_login() -> None:
    session = cast("Session", object())

    adapter = _adapter(port=5433, session=session)

    assert adapter.credentials == RdsIamCredentials(
        host=_ENDPOINT, port=5433, user="orders_service", region="us-east-1", session=session
    )
    assert _destination(adapter)["port"] == "5433"


def test_the_rest_of_libpq_s_grammar_stays_open() -> None:
    # Without this the factory would become a second spelling of the connection
    # string, and every parameter it had not thought of would be a reason not to
    # use it.
    destination = _destination(
        _adapter(params={"application_name": "orders-api", "connect_timeout": "5"})
    )

    assert destination["application_name"] == "orders-api"
    assert destination["connect_timeout"] == "5"
    assert destination["sslmode"] == "require"
    assert destination["gssencmode"] == "disable"


def test_verification_stronger_than_require_is_the_caller_s_to_ask_for() -> None:
    # `require` encrypts without verifying the server, so AWS's own guidance is
    # to verify against its certificate bundle. Raising the mode is the point of
    # leaving it open at all.
    destination = _destination(
        _adapter(params={"sslmode": "verify-full", "sslrootcert": "/etc/ssl/rds-bundle.pem"})
    )

    assert destination["sslmode"] == "verify-full"
    assert destination["sslrootcert"] == "/etc/ssl/rds-bundle.pem"


@pytest.mark.parametrize("weaker", ["disable", "allow", "prefer"])
def test_a_weaker_sslmode_is_refused_without_echoing_the_parameters(weaker: str) -> None:
    with pytest.raises(ValueError) as refused:
        _adapter(params={"sslmode": weaker, "options": "-c application_name=hunter2"})

    assert str(refused.value) == (
        "params must not weaken sslmode below require; an IAM token travels only over TLS."
    )
    assert "hunter2" not in str(refused.value)


@pytest.mark.parametrize("reserved", ["host", "port", "user", "dbname", "password"])
def test_what_the_token_is_bound_to_is_not_the_parameters_to_restate(reserved: str) -> None:
    # A `host` the token was not signed for authenticates nothing, and a
    # `password` beside an IAM token is two credentials for one login. The
    # refusal quotes nothing, because `params` is a place other secrets live.
    with pytest.raises(ValueError) as refused:
        _adapter(params={reserved: "hunter2"})

    assert str(refused.value) == (
        "params must not name host, port, user, dbname or password; the factory states those."
    )
    assert "hunter2" not in str(refused.value)


def test_retention_and_preparation_are_forwarded_untouched() -> None:
    pool = PoolOptions(min_size=2, max_size=20)

    adapter = _adapter(pool=pool, prepare_threshold=None)

    assert adapter.pool is pool
    assert adapter.prepare_threshold is None
    assert _adapter(pool=OnDemandOptions(max_size=3)).pool == OnDemandOptions(max_size=3)


def test_the_factory_resolves_nothing_and_opens_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # It returns configuration, exactly as a directly constructed adapter does:
    # no token is signed, no AWS credential chain runs, no socket is opened and
    # no maintenance worker starts, so building one at import time or before a
    # fork is as safe as building the adapter by hand.
    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("the factory must open no connection")

    monkeypatch.setattr(psycopg, "connect", refuse)
    before = threading.active_count()

    adapter = _adapter(pool=OnDemandOptions(max_size=3))

    assert threading.active_count() == before
    assert isinstance(adapter.credentials, RdsIamCredentials)
