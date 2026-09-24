from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Final, Protocol, runtime_checkable

__all__ = [
    "DRIVER_MANAGED",
    "Credential",
    "CredentialResolutionError",
    "CredentialSource",
    "DriverManaged",
    "Password",
]


@dataclass(frozen=True, slots=True)
class Password:
    """One login secret, and its own source.

    A constant credential needs no wrapper to be a :class:`CredentialSource`: it
    resolves to itself, so an application writes ``credentials=Password(...)``
    and a dynamic source returns ``Password(...)``. ``secret`` is kept out of
    this value's representation, because a repr is a place values get logged.
    """

    secret: str = field(repr=False)

    def resolve(self) -> Password:
        return self


type Credential = Password
"""The kinds of credential a source may produce.

One member today. A later bearer-token or client-certificate kind widens this
alias without renaming anything a provider already constructs.
"""


@runtime_checkable
class CredentialSource(Protocol):
    """Produces the credential for one physical connection, each time one is created.

    Runtime-checkable because an adapter probes an unknown object at its
    configuration boundary: a provider registers nothing, so ``Password``, an
    AWS token source, and a test's fake are all recognized structurally.
    """

    def resolve(self) -> Credential:
        """The credential to authenticate the next physical connection with.

        Raise :class:`CredentialResolutionError` where one cannot be produced.
        Any other exception is wrapped by the adapter with fixed text, so
        classification never depends on a provider's discipline — but the
        message of whatever is raised is the provider's to keep secret-free,
        because a chained cause travels with it.
        """
        ...


class DriverManaged:
    """Parallax supplies no secret; the driver and the server settle it themselves.

    Peer or trust authentication, a client certificate, Kerberos, or the driver's
    own environment (``PGPASSWORD``, ``.pgpass``, a ``service`` file) — each
    crosses this seam not at all. It is a DECLARATION beside the protocol rather
    than a source: it resolves nothing, so it is never forced through
    :meth:`CredentialSource.resolve` and :data:`Credential` stays a one-member
    alias. Requiring it to be spelled is what makes the choice visible on the
    line that configures an adapter.
    """

    __slots__ = ()
    _instance: ClassVar[DriverManaged | None] = None

    def __new__(cls) -> DriverManaged:
        if DriverManaged._instance is None:
            DriverManaged._instance = super().__new__(cls)
        return DriverManaged._instance

    def __init_subclass__(cls) -> None:
        raise TypeError("DriverManaged admits one instance and therefore no subclass")


DRIVER_MANAGED: Final[DriverManaged] = DriverManaged()
"""The one :class:`DriverManaged` declaration, recognized by identity."""


class CredentialResolutionError(Exception):
    """A source could not produce a credential, so no connection was authenticated.

    The message never carries a secret. A source that wraps a native failure
    keeps that discipline for its own message; what it chains as a cause is the
    provider's to police, since nothing here can scrub it.
    """
