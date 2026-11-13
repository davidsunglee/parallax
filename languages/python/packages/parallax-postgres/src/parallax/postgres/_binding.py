from __future__ import annotations

import functools
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Self

from parallax.core.internal.database_binding import (
    BINDING_DEFINITION_REJECTED,
    BINDING_SYNTAX_INVALID,
    BindingError,
    BindingIssue,
    BindingParts,
    LocationCodec,
    binding_document,
    binding_from_document,
)
from parallax.core.internal.dialect import POSTGRES, Dialect
from parallax.core.internal.metamodel import EntityIdentity

if TYPE_CHECKING:
    from collections.abc import Callable

    import yaml

__all__ = ["PostgresBinding", "PostgresLocation", "PostgresSequence", "PostgresTable"]


@dataclass(frozen=True, slots=True)
class PostgresLocation:
    """A PostgreSQL schema within the database the adapter's endpoint selects."""

    schema: str

    @property
    def qualifier(self) -> tuple[str, ...]:
        return (self.schema,)


@dataclass(frozen=True, slots=True)
class PostgresTable:
    """Overrides one mapping owner's schema, table name, or both.

    An omitted schema comes from the binding's namespace or default location;
    an omitted name is the model's declared table name.
    """

    schema: str | None = None
    name: str | None = None

    @property
    def location(self) -> PostgresLocation | None:
        return None if self.schema is None else PostgresLocation(self.schema)


@dataclass(frozen=True, slots=True)
class PostgresSequence:
    """Overrides one logical allocator's schema, sequence name, or both.

    An omitted schema comes from the binding's default location, never a
    namespace; an omitted name is the allocator key.
    """

    schema: str | None = None
    name: str | None = None

    @property
    def location(self) -> PostgresLocation | None:
        return None if self.schema is None else PostgresLocation(self.schema)


_CODEC: Final = LocationCodec(
    backend="postgres",
    keys=("schema",),
    location_type=PostgresLocation,
    table_type=PostgresTable,
    sequence_type=PostgresSequence,
    load=lambda components: PostgresLocation(components["schema"]),
    dump=lambda location: {"schema": location.schema},
    table=lambda location, name: PostgresTable(None if location is None else location.schema, name),
    sequence=lambda location, name: PostgresSequence(
        None if location is None else location.schema, name
    ),
)


@dataclass(frozen=True, slots=True, init=False, repr=False)
class PostgresBinding:
    """Where one deployment places a model's tables and sequences in PostgreSQL.

    ``default`` places every table and sequence nothing more specific places;
    ``namespaces`` places the tables of each exact Entity Namespace;
    ``entities`` overrides individual mapping owners, keyed by canonical Entity
    name; ``sequences`` overrides individual allocators, keyed by allocator name.
    The value is immutable and owns copies of the maps it was given, keyed by
    ``EntityIdentity`` for ``entities``. Construction, ``from_document``,
    ``from_json``, and ``from_yaml`` all raise :class:`~parallax.core.BindingError`
    with every problem at its document path.
    """

    default: PostgresLocation | None
    namespaces: Mapping[str, PostgresLocation]
    entities: Mapping[EntityIdentity, PostgresTable]
    sequences: Mapping[str, PostgresSequence]

    def __init__(
        self,
        *,
        default: PostgresLocation | None = None,
        namespaces: Mapping[str, PostgresLocation] | None = None,
        entities: Mapping[str, PostgresTable]
        | Mapping[EntityIdentity, PostgresTable]
        | None = None,
        sequences: Mapping[str, PostgresSequence] | None = None,
    ) -> None:
        document = binding_document(
            _CODEC,
            default=default,
            namespaces=namespaces,
            entities=entities,
            sequences=sequences,
        )
        self._adopt(binding_from_document(document, _CODEC))

    @property
    def dialect(self) -> Dialect:
        """The backend this binding places objects in."""
        return POSTGRES

    def _adopt(
        self, parts: BindingParts[PostgresLocation, PostgresTable, PostgresSequence]
    ) -> None:
        object.__setattr__(self, "default", parts.default)
        object.__setattr__(self, "namespaces", parts.namespaces)
        object.__setattr__(self, "entities", parts.entities)
        object.__setattr__(self, "sequences", parts.sequences)

    @classmethod
    def _from_parts(
        cls, parts: BindingParts[PostgresLocation, PostgresTable, PostgresSequence]
    ) -> Self:
        binding = cls.__new__(cls)
        binding._adopt(parts)
        return binding

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> Self:
        """The binding a decoded binding document describes."""
        return cls._from_parts(binding_from_document(document, _CODEC))

    @classmethod
    def from_json(cls, text: str | bytes) -> Self:
        """The binding a JSON binding document describes."""
        document = _decoded(text, json.loads, json.JSONDecodeError, "JSON")
        return cls._from_parts(binding_from_document(document, _CODEC))

    @classmethod
    def from_yaml(cls, text: str | bytes) -> Self:
        """The binding a YAML binding document describes, read under the YAML 1.2
        core schema: a plain scalar is null, a boolean, an integer, or a float
        only in that schema's spellings, and otherwise the string written."""
        import yaml

        loader = _yaml_loader()
        document = _decoded(
            text, lambda source: yaml.load(source, Loader=loader), yaml.YAMLError, "YAML"
        )
        return cls._from_parts(binding_from_document(document, _CODEC))

    def to_document(self) -> dict[str, object]:
        """This binding as a canonical binding document."""
        return binding_document(
            _CODEC,
            default=self.default,
            namespaces=self.namespaces,
            entities=self.entities,
            sequences=self.sequences,
        )

    def to_json(self) -> str:
        """This binding as canonical, byte-deterministic JSON text."""
        return json.dumps(self.to_document(), indent=2, ensure_ascii=False) + "\n"

    def to_yaml(self) -> str:
        """This binding as canonical, byte-deterministic YAML text.

        Every string a YAML 1.1 or 1.2 core reader would resolve to another type
        is quoted, so either reads it back as the string it is.
        """
        import yaml

        return yaml.dump(
            self.to_document(),
            Dumper=_yaml_dumper(),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.default,
                tuple(self.namespaces.items()),
                tuple(self.entities.items()),
                tuple(self.sequences.items()),
            )
        )

    def __repr__(self) -> str:
        return (
            f"PostgresBinding(default={self.default!r}, namespaces={dict(self.namespaces)!r}, "
            f"entities={dict(self.entities)!r}, sequences={dict(self.sequences)!r})"
        )


# The YAML 1.2 core schema's implicit resolvers (`m-database-binding`), each with
# the first characters a matching plain scalar can start with; the empty string
# is PyYAML's bucket for an empty plain scalar, which resolves to null.
_CORE_SCHEMA: Final[tuple[tuple[str, str, tuple[str, ...]], ...]] = (
    ("tag:yaml.org,2002:null", r"^(?:null|Null|NULL|~|)$", ("~", "n", "N", "")),
    ("tag:yaml.org,2002:bool", r"^(?:true|True|TRUE|false|False|FALSE)$", ("t", "T", "f", "F")),
    (
        "tag:yaml.org,2002:int",
        r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$",
        ("-", "+", *"0123456789"),
    ),
    (
        "tag:yaml.org,2002:float",
        r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
        r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$",
        ("-", "+", ".", *"0123456789"),
    ),
)


def _core_int(text: str) -> int:
    if text.lstrip("-+")[:2] in ("0o", "0x"):
        return int(text, 0)
    return int(text)


def _core_float(text: str) -> float:
    lowered = text.lower()
    if lowered.lstrip("-+") == ".inf":
        return float("-inf") if text.startswith("-") else float("inf")
    if lowered == ".nan":
        return float("nan")
    return float(text)


@functools.cache
def _yaml_loader() -> type[yaml.SafeLoader]:
    import yaml

    class _CoreLoader(yaml.SafeLoader):
        pass

    resolvers: dict[str, list[tuple[str, re.Pattern[str]]]] = {}
    for tag, pattern, first_characters in _CORE_SCHEMA:
        compiled = re.compile(pattern)
        for first in first_characters:
            resolvers.setdefault(first, []).append((tag, compiled))
    _CoreLoader.yaml_implicit_resolvers = resolvers

    def construct_int(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> int:
        return _core_int(str(loader.construct_scalar(node)))

    def construct_float(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> float:
        return _core_float(str(loader.construct_scalar(node)))

    _CoreLoader.add_constructor("tag:yaml.org,2002:int", construct_int)
    _CoreLoader.add_constructor("tag:yaml.org,2002:float", construct_float)
    return _CoreLoader


@functools.cache
def _yaml_dumper() -> type[yaml.SafeDumper]:
    import yaml

    class _BindingDumper(yaml.SafeDumper):
        pass

    # A plain scalar either schema resolves to a non-string must be quoted: the
    # 1.1 resolvers the dumper inherits cover PyYAML readers, and the core
    # schema's cover 1.2 readers.
    resolvers = {
        first: list(entries) for first, entries in yaml.SafeDumper.yaml_implicit_resolvers.items()
    }
    for tag, pattern, first_characters in _CORE_SCHEMA:
        compiled = re.compile(pattern)
        for first in first_characters:
            resolvers.setdefault(first, []).append((tag, compiled))
    _BindingDumper.yaml_implicit_resolvers = resolvers

    def represent_text(_dumper: yaml.SafeDumper, text: str) -> yaml.ScalarNode:
        # PyYAML folds a NEL into a space in every scalar style except double-quoted,
        # where it escapes it.
        style = '"' if "\x85" in text else None
        return yaml.ScalarNode("tag:yaml.org,2002:str", text, style=style)

    _BindingDumper.add_representer(str, represent_text)
    return _BindingDumper


def _decoded(
    text: str | bytes,
    decode: Callable[[str], object],
    error: type[Exception],
    format_name: str,
) -> object:
    try:
        source = text if isinstance(text, str) else text.decode("utf-8")
        document = decode(source)
    # PyYAML's scalar constructors raise these, not a YAMLError, for a scalar its
    # tag cannot convert, such as `!!int invalid` or the date `2026-02-30`.
    except (ValueError, LookupError, AttributeError, error) as exc:
        raise BindingError(
            BINDING_DEFINITION_REJECTED,
            (BindingIssue(BINDING_SYNTAX_INVALID, (), message=f"not well-formed {format_name}"),),
        ) from exc
    return document
