"""The deployed cluster's physical topology, read off its instances.

Every session here is IAM-authenticated with a token signed for the host it
reaches and verifies that host's certificate in full, so connecting at all
proves both on the writer endpoint, the reader endpoint, and each instance
endpoint. What each endpoint reaches is then established by the cluster's own
account of itself, before any Parallax routing claim depends on it.
"""

from __future__ import annotations

from typing import Any

from tests.provider_contract.aws._aws_support import instances

_WHERE = "select aurora_db_instance_identifier(), pg_is_in_recovery(), session_user"
_WRITER_INSTANCE = (
    "select server_id from aurora_replica_status() where session_id = 'MASTER_SESSION_ID'"
)
_TLS = "select ssl from pg_stat_ssl where pid = pg_backend_pid()"


def test_the_writer_endpoint_reaches_the_instance_the_cluster_names_its_writer(
    aws_run: Any,
) -> None:
    session = aws_run.session(aws_run.environment.writer_host)

    ((identifier, recovering, login),) = session.execute(_WHERE, [])
    ((writer,),) = session.execute(_WRITER_INSTANCE, [])

    assert identifier == writer
    assert {identifier} == instances(aws_run, "writer")
    assert recovering is False
    assert login == aws_run.environment.login


def test_the_reader_endpoint_reaches_a_reader_in_recovery(aws_run: Any) -> None:
    session = aws_run.session(aws_run.environment.reader_host)

    ((identifier, recovering, login),) = session.execute(_WHERE, [])

    assert identifier in instances(aws_run, "reader")
    assert recovering is True
    assert login == aws_run.environment.login


def test_each_instance_endpoint_reaches_its_own_instance_over_tls(aws_run: Any) -> None:
    for instance in aws_run.environment.instances:
        session = aws_run.session(instance.host)

        ((identifier, recovering, _login),) = session.execute(_WHERE, [])
        ((encrypted,),) = session.execute(_TLS, [])

        assert identifier == instance.identifier
        assert recovering is (instance.role == "reader")
        assert encrypted is True
