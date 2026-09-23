"""The RDS Postgres story, spelled once: an adapter already told what IAM needs.

This module is the engine-specific leaf of the credential provider, and the only
one that reaches an adapter. Its parent package composes nothing and imports no
driver, so a deployment on another engine installs the provider without one;
this module arrives with the ``postgres`` extra and the adapter it composes.

What it knows that a caller would otherwise have to remember: an IAM token is a
password, so it travels only over TLS; a token is signed for one hostname, port
and database user and proves nothing at another, so the endpoint the application
connects through is the endpoint it must be signed for; and a cluster is reached
through its own endpoint. Stating those three once is the whole reason this is a
factory rather than a documented recipe. What it does not know stays open
through ``params``, so it never becomes a second spelling of libpq's grammar.

The result is the shipped :class:`~parallax.postgres.PostgresAdapter` — a value,
not a wrapper: nothing here sits between an application and the adapter at
runtime, and nothing is resolved or opened while it is built.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, Unpack

import psycopg.conninfo

from parallax.aws._rds import RdsIamCredentials
from parallax.postgres import PostgresAdapter

if TYPE_CHECKING:
    from collections.abc import Mapping

    from botocore.session import Session

    from parallax.postgres import OnDemandOptions, PoolOptions

__all__ = ["rds_postgres"]

# What the token is signed for, plus the secret it stands in for. A connection
# that used any other value for one of these would present a token signed for
# something else, so the factory states them and `params` may not restate them.
_RESERVED = frozenset({"host", "port", "user", "dbname", "password"})
_WEAKER_THAN_REQUIRE = frozenset({"disable", "allow", "prefer"})

_RESERVED_REFUSAL = (
    "params must not name host, port, user, dbname or password; the factory states those."
)
_SSLMODE_REFUSAL = (
    "params must not weaken sslmode below require; an IAM token travels only over TLS."
)


class _AdapterOptions(TypedDict, total=False):
    """Everything about the adapter that is none of this factory's business."""

    pool: PoolOptions | OnDemandOptions
    prepare_threshold: int | None


def rds_postgres(
    *,
    host: str,
    user: str,
    database: str,
    region: str,
    port: int = 5432,
    params: Mapping[str, str] | None = None,
    session: Session | None = None,
    **adapter_options: Unpack[_AdapterOptions],
) -> PostgresAdapter:
    """Configure a Postgres adapter whose login authenticates with an RDS IAM token.

    ``host`` is the endpoint the application connects through — a cluster's own
    endpoint for Aurora — and, with ``port`` and ``user``, what each token is
    signed for. ``region`` is the token's credential scope and ``session`` an
    optional botocore session to resolve AWS credentials through.

    ``params`` carries the rest of libpq's grammar — ``application_name``,
    ``options``, ``connect_timeout``, ``sslrootcert`` — so this factory never
    becomes a second spelling of the connection string. It may raise
    ``sslmode`` to ``verify-ca`` or ``verify-full``; it may not weaken it, and
    it may not name what the token is bound to. Both refusals are fixed text,
    because ``params`` is a place other secrets live.

    Nothing here resolves a token, reaches AWS, or opens anything: the result is
    configuration, exactly as a directly constructed adapter is.
    """
    requested = dict(params or {})
    if _RESERVED & requested.keys():
        raise ValueError(_RESERVED_REFUSAL)
    if requested.get("sslmode", "require") in _WEAKER_THAN_REQUIRE:
        raise ValueError(_SSLMODE_REFUSAL)
    conninfo = psycopg.conninfo.make_conninfo(
        host=host,
        port=port,
        user=user,
        dbname=database,
        **{"sslmode": "require", **requested},
    )
    return PostgresAdapter(
        conninfo,
        credentials=RdsIamCredentials(
            host=host, port=port, user=user, region=region, session=session
        ),
        **adapter_options,
    )
