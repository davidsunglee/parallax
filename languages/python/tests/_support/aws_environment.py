"""The deployed AWS test environment, as the cloud suite reads it.

Infrastructure publishes one TestEnvironment record whose shape the schemas
beside it in ``infra/aws`` own. A record is validated against the schema of the
version it names and then normalized into one :class:`AwsTestEnvironment`, so the
suite works from a single value whichever supported version a deployment
published. While a new version rolls out, the previous version's schema stays as
``test-environment.v<N>.schema.json`` and keeps its normalizer here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from jsonschema import exceptions
from jsonschema.validators import validator_for

from tests._support.repo import REPO_ROOT

SCHEMA_DIRECTORY = REPO_ROOT / "infra" / "aws"
CURRENT_SCHEMA = "test-environment.schema.json"
_PREVIOUS_SCHEMA = re.compile(r"test-environment\.v(\d+)\.schema\.json")


class UnreadableEnvironmentError(ValueError):
    """A published record that no supported schema version accepts."""


@dataclass(frozen=True, slots=True)
class AwsInstance:
    identifier: str
    host: str
    role: Literal["writer", "reader"]


@dataclass(frozen=True, slots=True)
class AwsTestEnvironment:
    writer_host: str
    reader_host: str
    port: int
    region: str
    login: str
    cluster_id: str
    instances: tuple[AwsInstance, ...]
    ca_bundle_url: str

    @classmethod
    def from_record(cls, text: str, schemas: Path = SCHEMA_DIRECTORY) -> AwsTestEnvironment:
        """The environment a published record describes, refusing one that is not
        JSON, names no version, names one no schema here declares, or breaks its
        version's schema."""
        try:
            record: Any = json.loads(text)
        except json.JSONDecodeError as error:
            raise UnreadableEnvironmentError("the record is not JSON") from error
        if (
            not isinstance(record, dict)
            or type(cast("dict[str, Any]", record).get("schema")) is not int
        ):
            raise UnreadableEnvironmentError("the record names no schema version")
        fields = cast("dict[str, Any]", record)
        version: int = fields["schema"]
        schema = authored_schemas(schemas).get(version)
        normalize = NORMALIZERS.get(version)
        if schema is None or normalize is None:
            raise UnreadableEnvironmentError(
                f"schema version {version} is not one this suite reads"
            )
        _validate(schema, fields)
        return normalize(fields)


def _validate(schema: dict[str, Any], record: Mapping[str, Any]) -> None:
    validator = validator_for(schema)
    validator.check_schema(schema)
    error = cast(
        "exceptions.ValidationError | None",
        exceptions.best_match(validator(schema).iter_errors(record)),  # pyright: ignore[reportUnknownMemberType]
    )
    if error is not None:
        raise UnreadableEnvironmentError(f"the record breaks its schema: {error.message}")


def _declared_version(schema: Mapping[str, Any]) -> int:
    properties = cast("Mapping[str, Mapping[str, Any]]", schema["properties"])
    return int(properties["schema"]["const"])


def authored_schemas(directory: Path = SCHEMA_DIRECTORY) -> dict[int, dict[str, Any]]:
    """Every TestEnvironment schema authored in *directory*, by the version it
    declares: the current one, and any previous one still rolling out, whose file
    name must state the version it declares."""
    schemas: dict[int, dict[str, Any]] = {}
    for path in sorted(directory.glob("test-environment*.schema.json")):
        schema = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
        version = _declared_version(schema)
        previous = _PREVIOUS_SCHEMA.fullmatch(path.name)
        if path.name != CURRENT_SCHEMA and (previous is None or int(previous[1]) != version):
            raise ValueError(f"{path.name} does not name the version {version} it declares")
        schemas[version] = schema
    return schemas


def _from_version_1(record: Mapping[str, Any]) -> AwsTestEnvironment:
    instances = cast("list[Mapping[str, Any]]", record["instances"])
    return AwsTestEnvironment(
        writer_host=record["writer_host"],
        reader_host=record["reader_host"],
        port=record["port"],
        region=record["region"],
        login=record["login"],
        cluster_id=record["cluster_id"],
        instances=tuple(
            AwsInstance(identifier=entry["identifier"], host=entry["host"], role=entry["role"])
            for entry in instances
        ),
        ca_bundle_url=record["ca_bundle_url"],
    )


NORMALIZERS: Mapping[int, Callable[[Mapping[str, Any]], AwsTestEnvironment]] = {
    1: _from_version_1,
}
"""How each supported record version becomes the one environment value."""
