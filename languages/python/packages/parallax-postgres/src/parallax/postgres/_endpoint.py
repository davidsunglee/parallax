from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import psycopg
import psycopg.conninfo

from parallax.core.internal.db_port import DRIVER_MANAGED, CredentialSource, DriverManaged
from parallax.postgres._options import OnDemandOptions, PoolOptions, RetentionOptions

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["PostgresEndpoint"]

_TYPE_REFUSAL = "connection_string must be a string."
_SYNTAX_REFUSAL = (
    "Invalid PostgreSQL connection string; expected libpq keyword/value syntax or a PostgreSQL URI."
)
_PASSWORD_REFUSAL = "connection_string must not carry a password; supply it through credentials."
_CREDENTIALS_REFUSAL = "credentials takes a CredentialSource or DRIVER_MANAGED."


def _parsed(connection_string: str) -> Mapping[str, object]:
    """Prove the string is one the driver will accept, and disclose nothing if not.

    Parsing here is a spelling check and nothing more: it opens no socket,
    resolves no host, reads no service file, and proves neither that the
    destination exists nor that the credentials work. Those resolve when each
    physical connection is created, which is deliberate — immutable
    configuration must not freeze an environment that the deployment expects to
    change underneath it.

    The refusal is fixed text. A parser's own message can quote the input it
    rejected, and the input is a connection string: it can carry a password. So
    neither the string nor the native message reaches the message, the logs, or
    the displayed cause chain, and the native exception is suppressed as a cause
    rather than chained. This disclosure rule is specific to construction-time
    configuration errors — a failure to CONNECT later chains its cause normally,
    because by then nothing is quoting the caller's input back.

    The parse is returned rather than discarded so the password check below
    reads it instead of running a second one.
    """
    if type(connection_string) is not str:
        raise TypeError(_TYPE_REFUSAL)
    try:
        return psycopg.conninfo.conninfo_to_dict(connection_string)
    except psycopg.Error:
        raise ValueError(_SYNTAX_REFUSAL) from None


def _password_free(parsed: Mapping[str, object]) -> None:
    """Refuse a connection string that carries a secret, whatever ``credentials`` is.

    A secret has exactly one home: the credential source. The parse sees both
    libpq spellings — a ``password=`` keyword and a URI password — and it sees
    neither a ``service`` file nor ``PGPASSWORD``, which are libpq's own
    business under :data:`DRIVER_MANAGED` and lose to an explicit password by
    libpq's own precedence under a source.

    The refusal is the same fixed text the syntax refusal is, and for the same
    reason: the string may still carry other secrets, so it is never quoted.
    """
    if "password" in parsed:
        raise ValueError(_PASSWORD_REFUSAL)


def _credentials(value: object) -> None:
    """Refuse anything that is neither the declaration nor a source.

    :data:`DRIVER_MANAGED` is recognized by identity, since ``DriverManaged``
    admits one instance; a source is recognized structurally, which is what lets
    a ``Password``, a provider's token source, and a test's fake all pass
    without registering anything. A structural check sees only that the
    attribute exists, so the two ways it can exist without being resolvable are
    excluded here: an attribute that is not callable, and a source CLASS passed
    where one of its instances was meant — ``credentials=Password`` rather than
    ``credentials=Password(...)`` — whose ``resolve`` would be called with no
    instance to bind. Both would otherwise fail per connection, which a
    retaining pool retries until a caller's budget runs out rather than
    reporting here.

    The refusal quotes nothing: a value in this position can be a bare secret
    somebody meant to pass as a password.
    """
    if value is DRIVER_MANAGED:
        return
    if isinstance(value, type) or not isinstance(value, CredentialSource):
        raise TypeError(_CREDENTIALS_REFUSAL)
    if not callable(value.resolve):
        raise TypeError(_CREDENTIALS_REFUSAL)


def _retention(pool: object) -> RetentionOptions:
    if not isinstance(pool, PoolOptions | OnDemandOptions):
        raise TypeError(
            f"pool takes PoolOptions or OnDemandOptions (got {pool!r}); omit it for the "
            f"retaining defaults"
        )
    return pool


@dataclass(frozen=True, slots=True)
class PostgresEndpoint:
    """Where one route connects, how it logs in, and how it keeps connections.

    ``connection_string`` is libpq's own grammar — keyword/value pairs, a
    ``postgresql://`` URI, a ``service=`` reference, or the empty string, which
    asks libpq to take everything from the environment. It says WHERE, and it
    may not carry a password: one that does is refused here. It is stored
    exactly as given and kept out of this value's representation, because a
    connection string is still a place other secrets live and a repr is a place
    values get logged.

    ``credentials`` says HOW the login that string names authenticates, and is
    required: either a
    :class:`~parallax.core.internal.db_port.CredentialSource` — a
    :class:`~parallax.core.internal.db_port.Password`, or a provider's own source, asked
    where each physical connection is established — or
    :data:`~parallax.core.internal.db_port.DRIVER_MANAGED`, which declares that Parallax
    supplies no secret and leaves authentication to the driver and the server
    (peer, trust, a client certificate, Kerberos, or libpq's own environment:
    ``PGPASSWORD``, ``.pgpass``, a ``service`` file). There is no default and no
    ``None``, so which of the two a deployment chose is visible on the line. It
    is kept out of this value's representation for the same reason the string
    is: :class:`~parallax.core.internal.db_port.Password` hides its own secret, but a
    source is any object a provider wrote, and one holding broker material in an
    ordinary repr would otherwise reach every log line this value does.

    ``pool`` selects retention. Omitting it takes :class:`PoolOptions`' defaults;
    :class:`OnDemandOptions` keeps no idle connections instead. Change any of
    them by constructing a new value — ``dataclasses.replace`` works and
    revalidates — never by mutating this one, so a runtime already open cannot
    be reconfigured underneath its handle.

    Nothing about the endpoint's role is inferred from the string: the adapter
    field it is configured as says which route it serves.
    """

    connection_string: str = field(repr=False)
    credentials: CredentialSource | DriverManaged = field(repr=False, kw_only=True)
    pool: RetentionOptions = field(default_factory=PoolOptions, kw_only=True)

    def __post_init__(self) -> None:
        _password_free(_parsed(self.connection_string))
        _credentials(self.credentials)
        object.__setattr__(self, "pool", _retention(self.pool))
