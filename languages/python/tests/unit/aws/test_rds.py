"""The RDS IAM Credential Source: a local presign, on one client, per attempt. Docker-free.

No AWS is reached here and none is needed: a stub session hands out a stub
client, which is the whole of what the record talks to. What is graded is the
presign's inputs, that one client serves every resolution while each resolution
signs anew, that a native failure becomes a refusal carrying no token, and that
constructing the record runs no credential chain.

The last two build a real botocore session over an authored AWS config file,
because a credential helper that never answers is a wait only the real chain
can be asked to take.
"""

from __future__ import annotations

import dataclasses
import os
import shlex
import subprocess
import sys
import time
from typing import TYPE_CHECKING, cast

import botocore.session
import pytest
from botocore.config import Config

from parallax.aws import RdsIamCredentials, _rds
from parallax.core.db_port import CredentialResolutionError, CredentialSource, Password

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from botocore.session import Session

_ENDPOINT = "orders.cluster-abc.us-east-1.rds.amazonaws.com"

_UNANSWERING_HELPER = (
    f"{shlex.quote(sys.executable)} -c {shlex.quote('import time; time.sleep(300)')}"
)
_HELPER_BOUND = 1.0

_BoundedHelper = _rds._BoundedHelper  # pyright: ignore[reportPrivateUsage] - the helper the record bounds is module-private and its timeout path is what these prove

_WRAPPER_HELPER = (
    "import subprocess, sys\n"
    "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])\n"
    "import time; time.sleep(300)\n"
)
_WRAPPED_WORKER = (
    "import os, pathlib, sys, time\n"
    "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
    "for _ in range(600):\n"
    "    sys.stdout.write('x' * 4096)\n"
    "    sys.stdout.flush()\n"
    "    time.sleep(0.05)\n"
)


class _StubClient:
    """Stands in for the RDS client, recording what each presign was asked for."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.requests: list[dict[str, object]] = []
        self._failure = failure

    def generate_db_auth_token(
        self, DBHostname: str, Port: int, DBUsername: str, Region: str
    ) -> str:
        self.requests.append(
            {"DBHostname": DBHostname, "Port": Port, "DBUsername": DBUsername, "Region": Region}
        )
        if self._failure is not None:
            raise self._failure
        return f"token-{len(self.requests)}"


class _StubSession:
    """Stands in for a botocore session, recording what it is asked for and set to."""

    def __init__(self, client: _StubClient | None = None) -> None:
        self.client = client if client is not None else _StubClient()
        self.created: list[tuple[str, str | None]] = []
        self.configs: list[Config] = []
        self.variables: dict[str, object] = {}
        self.components: list[str] = []

    def create_client(self, service_name: str, region_name: str | None = None) -> _StubClient:
        self.created.append((service_name, region_name))
        return self.client

    def set_default_client_config(self, client_config: Config) -> None:
        self.configs.append(client_config)

    def set_config_variable(self, logical_name: str, value: object) -> None:
        self.variables[logical_name] = value

    def lazy_register_component(self, name: str, no_arg_factory: object) -> None:
        self.components.append(name)


def _credentials(session: _StubSession) -> RdsIamCredentials:
    return RdsIamCredentials(
        host=_ENDPOINT,
        port=5432,
        user="orders_service",
        region="us-east-1",
        session=cast("Session", session),
    )


def test_the_presign_names_the_endpoint_the_login_and_the_region() -> None:
    # A token proves nothing at an endpoint, a port, a user or a Region it was
    # not signed for, so what the record was configured with is exactly what the
    # request carries.
    session = _StubSession()

    _credentials(session).resolve()

    assert session.created == [("rds", "us-east-1")]
    assert session.client.requests == [
        {
            "DBHostname": _ENDPOINT,
            "Port": 5432,
            "DBUsername": "orders_service",
            "Region": "us-east-1",
        }
    ]


def test_every_resolution_signs_anew_on_the_one_client() -> None:
    # Creating a client runs the AWS credential chain; signing on it does not.
    # So the chain is paid once and each attempt gets a token of its own, which
    # is what lets a pool outlive the fifteen minutes any one token lasts.
    session = _StubSession()
    credentials = _credentials(session)

    produced = [credentials.resolve() for _ in range(3)]

    assert len(session.created) == 1
    assert len(session.client.requests) == 3
    assert produced == [Password("token-1"), Password("token-2"), Password("token-3")]
    assert all(isinstance(credential, Password) for credential in produced)
    assert "token-1" not in repr(produced[0])


def test_a_signing_failure_is_a_refusal_that_names_no_token() -> None:
    native = RuntimeError("Unable to locate credentials")
    session = _StubSession(_StubClient(failure=native))

    with pytest.raises(CredentialResolutionError) as refused:
        _credentials(session).resolve()

    assert str(refused.value) == "RDS IAM token could not be generated"
    assert refused.value.__cause__ is native


def test_the_record_is_a_frozen_credential_source_equal_by_what_it_signs_for() -> None:
    session = _StubSession()
    credentials = _credentials(session)

    assert isinstance(credentials, CredentialSource)
    with pytest.raises(dataclasses.FrozenInstanceError):
        credentials.host = "elsewhere"  # pyright: ignore[reportAttributeAccessIssue] - the frozen record's refusal at runtime is what this proves
    assert credentials == _credentials(session)
    assert credentials != dataclasses.replace(credentials, region="eu-west-1")
    # The session is configuration too: two records resolving AWS credentials
    # through different chains are different records.
    assert credentials != dataclasses.replace(credentials, session=cast("Session", _StubSession()))
    # A session can carry static keys and the signer is machinery, so neither
    # reaches a log line through the generated repr.
    assert "session" not in repr(credentials)
    assert "signer" not in repr(credentials)


def test_construction_resolves_no_aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    # Creating a client runs the credential chain, which on EC2 or ECS is a
    # metadata-service call — configuration must own nothing and reach nothing,
    # so the chain is paid on the first resolution and never before it.
    sessions: list[_StubSession] = []

    def _session() -> _StubSession:
        sessions.append(_StubSession())
        return sessions[-1]

    monkeypatch.setattr(botocore.session, "get_session", _session)

    credentials = RdsIamCredentials(
        host=_ENDPOINT, port=5432, user="orders_service", region="us-east-1"
    )
    assert sessions == []

    assert credentials.resolve() == Password("token-1")
    assert len(sessions) == 1
    assert sessions[0].created == [("rds", "us-east-1")]

    credentials.resolve()
    assert len(sessions) == 1


def test_a_session_the_record_builds_bounds_the_chain_it_resolves_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `resolve` runs where nothing above it can interrupt it. The chain's own
    # clients — STS and SSO included — take their bounds from the session's
    # default configuration, and the instance metadata service, reached through
    # a fetcher rather than a client, takes its from the session's config
    # variables. What is graded is that neither is left at botocore's own
    # defaults, rather than the particular numbers chosen.
    session = _StubSession()
    monkeypatch.setattr(botocore.session, "get_session", lambda: session)

    RdsIamCredentials(
        host=_ENDPOINT, port=5432, user="orders_service", region="us-east-1"
    ).resolve()

    # botocore installs a Config's options as instance attributes in `__init__`
    # and its published stubs declare none of them, so they are read off the
    # instance dictionary rather than suppressed one by one.
    (config,) = session.configs
    bounds = vars(config)
    assert 0 < bounds["connect_timeout"] < 60
    assert 0 < bounds["read_timeout"] < 60
    # botocore reads `max_attempts` as retries after the initial request and
    # `total_max_attempts` as the whole budget, so the budget is spelled whole.
    assert "max_attempts" not in bounds["retries"]
    assert 0 < bounds["retries"]["total_max_attempts"] < 4
    assert session.variables == {
        "metadata_service_timeout": bounds["connect_timeout"],
        "metadata_service_num_attempts": bounds["retries"]["total_max_attempts"],
    }
    # A helper command is neither a client call nor a fetcher call, so the
    # record supplies the credential chain itself to bound the one wait left.
    assert session.components == ["credential_provider"]


def test_an_injected_session_is_used_exactly_as_it_was_given() -> None:
    # It is the caller's session, carrying whatever bounds and whatever identity
    # they built it with, so the record reconfigures nothing on it.
    session = _StubSession()

    _credentials(session).resolve()

    assert session.configs == []
    assert session.variables == {}
    assert session.components == []


def _resolving_through(config: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point a real botocore session at an authored AWS config and nothing else."""
    config_file = tmp_path / "config"
    config_file.write_text(config, encoding="utf-8")
    for ambient in [name for name in os.environ if name.startswith("AWS_")]:
        monkeypatch.delenv(ambient)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "absent-credentials"))
    monkeypatch.setenv("AWS_PROFILE", "app")
    monkeypatch.setattr(_rds, "_CHAIN_PROCESS_TIMEOUT", _HELPER_BOUND)


def _refusal_from_a_helper_that_never_answers() -> float:
    credentials = RdsIamCredentials(
        host=_ENDPOINT, port=5432, user="orders_service", region="us-east-1"
    )
    started = time.monotonic()
    with pytest.raises(CredentialResolutionError) as refused:
        credentials.resolve()
    waited = time.monotonic() - started

    assert str(refused.value) == "RDS IAM token could not be generated"
    assert isinstance(refused.value.__cause__, subprocess.TimeoutExpired)
    return waited


def test_a_profile_credential_helper_that_never_answers_is_given_up_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # botocore waits on a profile's helper command with no timeout of its own,
    # and `resolve` runs on an acquiring caller's thread or a pool's own
    # background path, where nothing can interrupt it. So the wait is the
    # record's to end: a helper that sleeps for five minutes costs one attempt,
    # not the pool.
    _resolving_through(
        f"[profile app]\ncredential_process = {_UNANSWERING_HELPER}\n", tmp_path, monkeypatch
    )

    assert _refusal_from_a_helper_that_never_answers() < 30


def test_a_helper_reached_through_an_assume_role_source_profile_is_given_up_on_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A source profile's providers are built when the role is resolved rather
    # than when the chain is, so the same helper is reached through a builder
    # the chain hands out later. The bound has to hold there as well, and no
    # role is ever assumed here: the wait ends before STS is reached.
    _resolving_through(
        "[profile app]\n"
        "role_arn = arn:aws:iam::123456789012:role/orders\n"
        "source_profile = helper\n"
        "\n"
        f"[profile helper]\ncredential_process = {_UNANSWERING_HELPER}\n",
        tmp_path,
        monkeypatch,
    )

    assert _refusal_from_a_helper_that_never_answers() < 30


def _sleeping_helper() -> _BoundedHelper:
    return _BoundedHelper(
        [sys.executable, "-c", "import time; time.sleep(300)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _settles(condition: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_a_helper_given_up_on_leaves_no_pipe_of_its_own_open() -> None:
    # The expiry leaves the process as the cause of a refusal the pool retains
    # as `last_refusal`, and that traceback retains the helper. A pipe left open
    # here would therefore stay open for as long as the refusal does, so giving
    # up closes both ends the source holds and reaps what it killed.
    helper = _sleeping_helper()

    with pytest.raises(subprocess.TimeoutExpired):
        helper.communicate(None, 0.2)

    assert helper.stdout is not None
    assert helper.stderr is not None
    assert helper.stdout.closed
    assert helper.stderr.closed
    assert helper.returncode is not None


def test_a_helper_given_up_on_leaves_no_worker_writing_credentials_behind(
    tmp_path: Path,
) -> None:
    # Killing the helper does not reach a worker it spawned, which inherited the
    # pipe rather than the signal. Closing the read end is what ends it: writing
    # the credential document is what such a process exists to do, and by then
    # nothing is reading.
    worker_pid = tmp_path / "worker.pid"
    helper = _BoundedHelper(
        [sys.executable, "-c", _WRAPPER_HELPER, _WRAPPED_WORKER, str(worker_pid)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert _settles(lambda: worker_pid.exists() and worker_pid.read_text() != "")
    worker = int(worker_pid.read_text())

    with pytest.raises(subprocess.TimeoutExpired):
        helper.communicate(None, 0.2)

    assert _settles(lambda: not _alive(worker))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
