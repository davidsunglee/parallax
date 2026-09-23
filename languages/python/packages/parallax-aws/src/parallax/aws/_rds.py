"""AWS RDS IAM database authentication as a Credential Source.

An RDS IAM token is a SigV4-presigned URL bound to a hostname, a port, a
database user, and a Region, which the server accepts in place of a password and
which stops being accepted fifteen minutes after it was signed. Signing is
local: what can block is botocore finding or refreshing the AWS credentials to
sign with, which is why the record bounds that I/O and why its client is created
on first use rather than while an adapter is being configured.

A connection the server has already accepted is never disturbed by its token
ageing out, so this source holds no cache and runs no refresh thread: each call
signs anew. When that happens is the port's rule, not this module's — see
``core/spec/m-db-port.md``, "Configuration carries where, and a Credential
Source carries how".
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, cast

import botocore.session
from botocore.config import Config

from parallax.core.db_port import CredentialResolutionError, Password

if TYPE_CHECKING:
    from botocore.client import BaseClient
    from botocore.session import Session

__all__ = ["RdsIamCredentials"]

_TOKEN_REFUSAL = "RDS IAM token could not be generated"

# What one credential-chain call may cost before the source gives up. The chain
# reaches the instance metadata service, an ECS task-role endpoint, STS or SSO,
# and botocore's own default is sixty seconds a side with five attempts — a wait
# the seam forbids, because a source runs where nothing above it can interrupt
# it. The budget is attempts in total, the first one included.
_CHAIN_CONNECT_TIMEOUT = 2.0
_CHAIN_READ_TIMEOUT = 2.0
_CHAIN_ATTEMPTS = 2


class _RdsTokenClient(Protocol):
    """The one RDS-client operation this module calls.

    botocore attaches ``generate_db_auth_token`` to an RDS client when the
    client is created, so it is on no class a type checker can read it off.
    """

    def generate_db_auth_token(
        self, DBHostname: str, Port: int, DBUsername: str, Region: str
    ) -> str: ...


def _bounded_session() -> Session:
    """A botocore session whose credential chain bounds its own network calls.

    The default client configuration reaches every client the session creates,
    the STS and SSO clients the chain builds internally included. The instance
    metadata service is reached through a fetcher rather than a client and takes
    its bounds from the session's own configuration, which is why that pair is
    set beside the client default rather than covered by it.

    One wait stays outside both: botocore runs a profile's ``credential_process``
    and waits on it with no timeout, so there the bound is the command's.
    """
    session = botocore.session.get_session()
    session.set_default_client_config(
        Config(
            connect_timeout=_CHAIN_CONNECT_TIMEOUT,
            read_timeout=_CHAIN_READ_TIMEOUT,
            retries={"total_max_attempts": _CHAIN_ATTEMPTS, "mode": "standard"},
        )
    )
    session.set_config_variable("metadata_service_timeout", _CHAIN_CONNECT_TIMEOUT)
    session.set_config_variable("metadata_service_num_attempts", _CHAIN_ATTEMPTS)
    return session


class _TokenSigner:
    """The RDS client a source signs on, created once and then kept.

    Creating a client runs the AWS credential chain, which on EC2 or ECS is a
    metadata-service call, so it cannot happen while configuration is being
    built. botocore clients are thread-safe and botocore sessions are not, so
    the one creation is serialized here and every pool worker afterwards signs
    on the same client.
    """

    __slots__ = ("_client", "_lock", "_region", "_session")

    def __init__(self, session: Session | None, region: str) -> None:
        self._session = session
        self._region = region
        self._lock = threading.Lock()
        self._client: _RdsTokenClient | None = None

    def client(self) -> _RdsTokenClient:
        with self._lock:
            if self._client is None:
                session = self._session if self._session is not None else _bounded_session()
                created: BaseClient = session.create_client("rds", region_name=self._region)
                self._client = cast("_RdsTokenClient", created)
            return self._client


@dataclass(frozen=True, slots=True)
class RdsIamCredentials:
    """Authenticates an RDS or Aurora Postgres login with an IAM token.

    ``host``, ``port`` and ``user`` are what the token is signed for and must be
    what the connection then uses: a token signed for one endpoint proves
    nothing at another, so a cluster reached through its own endpoint is signed
    for that endpoint. ``region`` is the token's credential scope.

    ``session`` is a botocore session to resolve AWS credentials through. Left
    absent, the record builds one whose credential chain bounds its own network
    calls; an injected one is used exactly as given and never reconfigured, so
    its owner keeps whatever bounds it was built with.
    """

    host: str
    port: int
    user: str
    region: str
    session: Session | None = field(default=None, repr=False)
    _signer: _TokenSigner = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_signer", _TokenSigner(self.session, self.region))

    def resolve(self) -> Password:
        try:
            token = self._signer.client().generate_db_auth_token(
                DBHostname=self.host, Port=self.port, DBUsername=self.user, Region=self.region
            )
        except Exception as exc:
            raise CredentialResolutionError(_TOKEN_REFUSAL) from exc
        return Password(token)
