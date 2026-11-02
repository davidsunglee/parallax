"""The cloud suite's reading of a published TestEnvironment record, over
synthetic records: nothing here acquires a parameter or a credential."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests._support.aws_environment import (
    CURRENT_SCHEMA,
    NORMALIZERS,
    SCHEMA_DIRECTORY,
    AwsInstance,
    AwsTestEnvironment,
    UnreadableEnvironmentError,
    authored_schemas,
)


def _record(**changes: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema": 1,
        "writer_host": "parallax-ci.cluster-abc.us-east-2.rds.amazonaws.com",
        "reader_host": "parallax-ci.cluster-ro-abc.us-east-2.rds.amazonaws.com",
        "port": 5432,
        "region": "us-east-2",
        "login": "parallax_conformance_login",
        "cluster_id": "parallax-ci",
        "instances": [
            {
                "identifier": "parallax-ci-writer",
                "host": "parallax-ci-writer.abc.us-east-2.rds.amazonaws.com",
                "role": "writer",
            },
            {
                "identifier": "parallax-ci-reader",
                "host": "parallax-ci-reader.abc.us-east-2.rds.amazonaws.com",
                "role": "reader",
            },
        ],
        "ca_bundle_url": "https://truststore.pki.rds.amazonaws.com/us-east-2/us-east-2-bundle.pem",
    }
    record.update(changes)
    return record


def test_a_conforming_record_becomes_one_environment_value() -> None:
    environment = AwsTestEnvironment.from_record(json.dumps(_record()))

    assert environment == AwsTestEnvironment(
        writer_host="parallax-ci.cluster-abc.us-east-2.rds.amazonaws.com",
        reader_host="parallax-ci.cluster-ro-abc.us-east-2.rds.amazonaws.com",
        port=5432,
        region="us-east-2",
        login="parallax_conformance_login",
        cluster_id="parallax-ci",
        instances=(
            AwsInstance(
                "parallax-ci-writer", "parallax-ci-writer.abc.us-east-2.rds.amazonaws.com", "writer"
            ),
            AwsInstance(
                "parallax-ci-reader", "parallax-ci-reader.abc.us-east-2.rds.amazonaws.com", "reader"
            ),
        ),
        ca_bundle_url="https://truststore.pki.rds.amazonaws.com/us-east-2/us-east-2-bundle.pem",
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{", "the record is not JSON"),
        ("[]", "the record names no schema version"),
        (json.dumps(_record(schema="1")), "the record names no schema version"),
        (json.dumps(_record(schema=True)), "the record names no schema version"),
        (json.dumps(_record(schema=7)), "schema version 7 is not one this suite reads"),
        (json.dumps(_record(port=0)), "the record breaks its schema"),
        (json.dumps(_record(writer_host="db.example.com")), "the record breaks its schema"),
        (json.dumps(_record(extra=1)), "the record breaks its schema"),
        (
            json.dumps(_record(instances=_record()["instances"][:1])),
            "the record breaks its schema",
        ),
    ],
)
def test_a_record_no_supported_version_accepts_is_refused(text: str, message: str) -> None:
    with pytest.raises(UnreadableEnvironmentError, match=message):
        AwsTestEnvironment.from_record(text)


def test_every_authored_schema_version_has_a_normalizer_and_no_other_does() -> None:
    assert set(authored_schemas()) == set(NORMALIZERS)


def _rolling_out(tmp_path: Path) -> Path:
    """A schema directory mid-rollout: the current schema bumped to version 2,
    and version 1 kept beside it under its versioned name."""
    current = json.loads((SCHEMA_DIRECTORY / CURRENT_SCHEMA).read_text(encoding="utf-8"))
    shutil.copyfile(SCHEMA_DIRECTORY / CURRENT_SCHEMA, tmp_path / "test-environment.v1.schema.json")
    current["properties"]["schema"]["const"] = 2
    (tmp_path / CURRENT_SCHEMA).write_text(json.dumps(current), encoding="utf-8")
    return tmp_path


def test_a_previous_version_still_rolling_out_is_read_through_its_own_schema(
    tmp_path: Path,
) -> None:
    schemas = _rolling_out(tmp_path)

    assert set(authored_schemas(schemas)) == {1, 2}
    environment = AwsTestEnvironment.from_record(json.dumps(_record()), schemas)
    assert environment.login == "parallax_conformance_login"
    with pytest.raises(UnreadableEnvironmentError, match="schema version 2 is not one"):
        AwsTestEnvironment.from_record(json.dumps(_record(schema=2)), schemas)


def test_a_previous_schema_must_be_named_for_the_version_it_declares(tmp_path: Path) -> None:
    schemas = _rolling_out(tmp_path)
    (schemas / "test-environment.v1.schema.json").rename(
        schemas / "test-environment.v3.schema.json"
    )

    with pytest.raises(ValueError, match=r"test-environment\.v3\.schema\.json does not name"):
        authored_schemas(schemas)
