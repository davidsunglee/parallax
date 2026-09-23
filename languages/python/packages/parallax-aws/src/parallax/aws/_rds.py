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

import subprocess
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, cast

import botocore.session
from botocore.config import Config
from botocore.credentials import AssumeRoleProvider, ProcessProvider, create_credential_resolver

from parallax.core.db_port import CredentialResolutionError, Password

if TYPE_CHECKING:
    from botocore.client import BaseClient
    from botocore.credentials import CredentialProvider, CredentialResolver
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

# What a profile's `credential_process` may take before the source gives up on
# it. A helper command makes a call of its own — a vault, an SSO endpoint, a
# security key someone has to touch — so it is allowed longer than one socket
# wait, and a deployment whose helper needs longer than this injects a session.
_CHAIN_PROCESS_TIMEOUT = 5.0

# Where ``Popen.communicate`` buffers what it has read, on the process itself,
# so an interrupted call can resume — one name per platform implementation.
_READ_BUFFERS = ("_fileobj2output", "_stdout_buff", "_stderr_buff")


class _RdsTokenClient(Protocol):
    """The one RDS-client operation this module calls.

    botocore attaches ``generate_db_auth_token`` to an RDS client when the
    client is created, so it is on no class a type checker can read it off.
    """

    def generate_db_auth_token(
        self, DBHostname: str, Port: int, DBUsername: str, Region: str
    ) -> str: ...


class _BoundedHelper(subprocess.Popen[bytes]):
    """A credential helper the source stops waiting on.

    botocore waits on a profile's ``credential_process`` with no timeout of its
    own, and it waits where nothing above the source can interrupt it, so the
    wait ends here, and the helper is killed and let go of when it does.
    """

    def communicate(
        self, input: bytes | None = None, timeout: float | None = None
    ) -> tuple[bytes, bytes]:
        try:
            return super().communicate(
                input, _CHAIN_PROCESS_TIMEOUT if timeout is None else timeout
            )
        except subprocess.TimeoutExpired as expiry:
            self.kill()
            self._let_go()
            raise _without_what_the_helper_wrote(expiry) from None

    def _let_go(self) -> None:
        """Close the killed helper's pipes, forget what it wrote, then reap it.

        The expiry travels out as the cause of a refusal a caller may hold on
        to, and its traceback holds this helper, so whatever is still held here
        stays held for as long as that refusal does — a descriptor for an open
        pipe, and the credential document itself for the bytes already read off
        one. Nothing resumes the interrupted call those bytes were buffered
        for, because the helper has been killed. Closing the read ends is also
        what ends a descendant the helper left behind: writing the credential
        document is what such a process exists to do, and once it does there is
        nothing reading. A descendant that writes nothing is one the helper
        meant to outlive it, which is not the source's to kill. Reaping last
        waits on the killed helper alone rather than on whatever else holds its
        pipes.
        """
        for pipe in (self.stdout, self.stderr):
            if pipe is not None:
                pipe.close()
        for name in _READ_BUFFERS:
            buffered: dict[object, list[bytes]] | list[bytes] | None = getattr(self, name, None)
            if buffered is not None:
                buffered.clear()
        self.wait()


def _without_what_the_helper_wrote(
    expiry: subprocess.TimeoutExpired,
) -> subprocess.TimeoutExpired:
    """The expiry with the bytes it captured dropped from it.

    ``communicate`` attaches what it had already read to the expiry it raises,
    and what a credential helper writes on stdout is the credential document.
    That expiry leaves here as the cause of a refusal a caller may hold on to
    and may log, and ``core/spec/m-db-port.md`` lets nothing a source raises
    carry the secret, so it keeps the command and the budget it overran and
    nothing else. Dropping the traceback drops the ``communicate`` frames
    holding the same bytes in their locals; re-raising puts this module's own
    frame back.
    """
    expiry.output = None
    expiry.stderr = None
    return expiry.with_traceback(None)


class _BuildsProfileProviders(Protocol):
    def providers(
        self, profile_name: str, disable_env_vars: bool = False
    ) -> list[CredentialProvider]: ...


class _RunsCredentialHelper(Protocol):
    """Where botocore's process provider keeps what it runs a helper with.

    Both this and the builder below are taken as constructor arguments and kept
    privately, so a chain botocore has already built is bounded through the
    attributes it keeps them on — which no class a type checker can read.
    """

    _popen: type[subprocess.Popen[bytes]]


class _AssumesRole(Protocol):
    _profile_provider_builder: _BuildsProfileProviders | None


class _BoundedProfileProviders:
    """An assume-role source profile's providers, built with the same bound.

    A source profile's chain is built when the role is resolved rather than when
    the session's chain is, so a helper reached that way is bounded here.
    """

    def __init__(self, builder: _BuildsProfileProviders) -> None:
        self._builder = builder

    def providers(
        self, profile_name: str, disable_env_vars: bool = False
    ) -> list[CredentialProvider]:
        return _bounded_helpers(self._builder.providers(profile_name, disable_env_vars))


def _bounded_helpers(providers: list[CredentialProvider]) -> list[CredentialProvider]:
    for provider in providers:
        if isinstance(provider, ProcessProvider):
            runs = cast("_RunsCredentialHelper", provider)
            runs._popen = _BoundedHelper  # pyright: ignore[reportPrivateUsage] - botocore takes the helper runner as a constructor argument and keeps it here
        elif isinstance(provider, AssumeRoleProvider):
            role = cast("_AssumesRole", provider)
            builder = role._profile_provider_builder  # pyright: ignore[reportPrivateUsage] - botocore keeps an assume-role profile's provider builder here
            if builder is not None:
                bounded = _BoundedProfileProviders(builder)
                role._profile_provider_builder = bounded  # pyright: ignore[reportPrivateUsage] - the wrapped builder goes back on the same attribute botocore reads
    return providers


def _bounded_chain(session: Session, region: str) -> CredentialResolver:
    """The session's credential chain, bounding every helper command it may run.

    botocore builds this chain itself the first time a client is created, for
    the region that client resolved; it is built here instead, for the region
    the RDS client will be created in, so the ``credential_process`` providers
    in it are bounded before anything can run them. It is built when botocore
    asks for it rather than with the session, so an adapter that never connects
    reads no configuration files.
    """
    resolver = create_credential_resolver(session, region_name=region)
    _bounded_helpers(resolver.providers)
    return resolver


def _bounded_session(region: str) -> Session:
    """A botocore session whose credential chain bounds its own waiting.

    The default client configuration reaches every client the session creates,
    the STS and SSO clients the chain builds internally included. The instance
    metadata service is reached through a fetcher rather than a client and takes
    its bounds from the session's own configuration, which is why that pair is
    set beside the client default rather than covered by it. A profile's
    ``credential_process`` is neither: it is a command botocore waits on, and
    the chain registered here is what bounds that wait.
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
    session.lazy_register_component("credential_provider", lambda: _bounded_chain(session, region))
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
                session = (
                    self._session if self._session is not None else _bounded_session(self._region)
                )
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
