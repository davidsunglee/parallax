"""Independent reading of m-database-binding binding documents.

A binding document is judged by a *reader* for one backend: the backend whose
location shape every section uses. :func:`normalize_binding` either returns the
document's normalized form — every empty section omitted, every map in
canonical key order — or raises :class:`BindingRejection` carrying every
definition issue as a ``(path, code)`` pair in canonical order, the way
m-database-binding defines them. :func:`resolve_binding` then places one
model's mapping owners and logical allocators under a normalized document, or
refuses with every resolution issue.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .case import Model

import yaml

from .corpus_yaml import load_corpus_yaml

__all__ = [
    "BINDING_REJECTED_RULES",
    "LOCATION_KEYS",
    "BindingIssue",
    "BindingRejection",
    "PhysicalTable",
    "Placement",
    "normalize_binding",
    "parse_binding_text",
    "resolve_binding",
]

LOCATION_KEYS: dict[str, str] = {"postgres": "schema", "mariadb": "database"}
"""Each backend's one location key: a PostgreSQL schema, a MariaDB database."""

BINDING_REJECTED_RULES: frozenset[str] = frozenset(
    {
        "binding-syntax-invalid",
        "binding-value-invalid",
        "binding-field-unknown",
        "binding-field-missing",
        "binding-version-unsupported",
        "binding-backend-mismatch",
        "binding-namespace-key-invalid",
        "binding-entity-key-invalid",
        "binding-sequence-key-invalid",
        "binding-identifier-invalid",
        "binding-entity-unknown",
        "binding-entity-owns-no-table",
        "binding-namespace-unknown",
        "binding-sequence-unknown",
        "binding-table-unresolved",
        "binding-sequence-unresolved",
        "binding-table-collision",
        "binding-sequence-collision",
        "binding-sequence-table-collision",
    }
)
"""Every issue code a binding refusal of either phase carries (m-database-binding)."""

_NAMESPACE = re.compile(r"[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*")
_CANONICAL_ENTITY = re.compile(r"([a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*\.)?[A-Z][A-Za-z0-9]*")
_SECTIONS = ("format_version", "backend", "default", "namespaces", "entities", "sequences")


@dataclass(frozen=True, order=True)
class BindingIssue:
    """One definition issue; canonical order is path first, then code."""

    path: tuple[str, ...]
    code: str


class BindingRejection(Exception):
    """A reader refused a binding document; ``issues`` is canonically ordered."""

    def __init__(self, issues: set[BindingIssue]) -> None:
        self.issues = tuple(sorted(issues))
        super().__init__(", ".join(f"{i.code} at {list(i.path)}" for i in self.issues))


def parse_binding_text(text: str, fmt: str) -> Any:
    """Decode binding text; a malformed document is a ``binding-syntax-invalid`` rejection."""
    try:
        return json.loads(text) if fmt == "json" else load_corpus_yaml(text)
    # PyYAML's scalar constructors raise these, not a YAMLError, for a scalar its
    # tag cannot convert, such as `!!int invalid`.
    except (ValueError, LookupError, AttributeError, yaml.YAMLError) as exc:
        raise BindingRejection({BindingIssue((), "binding-syntax-invalid")}) from exc


def _entity_order(key: str) -> tuple[str, str]:
    namespace, _, name = key.rpartition(".")
    return (namespace, name)


class _Judge:
    def __init__(self, reader: str) -> None:
        self.reader = reader
        self.location_key = LOCATION_KEYS[reader]
        self.issues: set[BindingIssue] = set()

    def flag(self, path: tuple[str, ...], code: str) -> None:
        self.issues.add(BindingIssue(path, code))

    def identifier(self, value: Any, path: tuple[str, ...]) -> bool:
        if not isinstance(value, str):
            self.flag(path, "binding-value-invalid")
            return False
        if value == "":
            self.flag(path, "binding-identifier-invalid")
            return False
        return True

    def closed(self, value: Any, path: tuple[str, ...], allowed: set[str]) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            self.flag(path, "binding-value-invalid")
            return None
        for key in value:
            if key not in allowed:
                self.flag((*path, str(key)), "binding-field-unknown")
        return value

    def location(self, value: Any, path: tuple[str, ...]) -> dict[str, str] | None:
        fields = self.closed(value, path, {self.location_key})
        if fields is None:
            return None
        if self.location_key not in fields:
            self.flag((*path, self.location_key), "binding-field-missing")
            return None
        component = fields[self.location_key]
        if not self.identifier(component, (*path, self.location_key)):
            return None
        return {self.location_key: component}

    def entry(self, value: Any, path: tuple[str, ...], name_key: str) -> dict[str, str] | None:
        fields = self.closed(value, path, {self.location_key, name_key})
        if fields is None:
            return None
        normalized: dict[str, str] = {}
        ok = True
        for key in (self.location_key, name_key):
            if key in fields:
                if self.identifier(fields[key], (*path, key)):
                    normalized[key] = fields[key]
                else:
                    ok = False
        return normalized if ok else None

    def section(
        self,
        document: dict[str, Any],
        name: str,
        key_valid: Callable[[Any], bool],
        key_code: str,
        value: Callable[[Any, tuple[str, ...]], dict[str, str] | None],
        order: Callable[[str], Any],
    ) -> dict[str, dict[str, str]]:
        if name not in document:
            return {}
        raw = document[name]
        if not isinstance(raw, dict):
            self.flag((name,), "binding-value-invalid")
            return {}
        entries: dict[str, dict[str, str]] = {}
        for key, item in raw.items():
            path = (name, str(key))
            good_key = isinstance(key, str) and key_valid(key)
            if not good_key:
                self.flag(path, key_code)
            judged = value(item, path)
            if good_key and judged is not None:
                entries[key] = judged
        return {key: entries[key] for key in sorted(entries, key=order)}

    def envelope(self, document: dict[str, Any]) -> bool:
        """Flag unknown sections and an unreadable envelope; ``False`` stops judging."""
        for key in document:
            if key not in _SECTIONS:
                self.flag((str(key),), "binding-field-unknown")
        readable = True
        version = document.get("format_version")
        if "format_version" not in document:
            self.flag(("format_version",), "binding-field-missing")
            readable = False
        elif type(version) is not int or version != 1:
            self.flag(("format_version",), "binding-version-unsupported")
            readable = False
        if "backend" not in document:
            self.flag(("backend",), "binding-field-missing")
            readable = False
        elif document["backend"] != self.reader:
            self.flag(("backend",), "binding-backend-mismatch")
            readable = False
        return readable


def normalize_binding(document: Any, reader: str) -> dict[str, Any]:
    """The normalized form of *document* for *reader*, or :class:`BindingRejection`."""
    judge = _Judge(reader)
    if not isinstance(document, dict):
        raise BindingRejection({BindingIssue((), "binding-value-invalid")})
    if not judge.envelope(document):
        raise BindingRejection(judge.issues)

    normalized: dict[str, Any] = {"format_version": 1, "backend": reader}
    if "default" in document:
        default = judge.location(document["default"], ("default",))
        if default is not None:
            normalized["default"] = default
    sections: tuple[
        tuple[str, Callable[[Any], bool], str, Callable[..., Any], Callable[..., Any]], ...
    ] = (
        ("namespaces", _matches(_NAMESPACE), "binding-namespace-key-invalid", judge.location, str),
        (
            "entities",
            _matches(_CANONICAL_ENTITY),
            "binding-entity-key-invalid",
            lambda value, path: judge.entry(value, path, "table"),
            _entity_order,
        ),
        (
            "sequences",
            lambda key: key != "",
            "binding-sequence-key-invalid",
            lambda value, path: judge.entry(value, path, "sequence"),
            str,
        ),
    )
    for name, key_valid, key_code, value, order in sections:
        entries = judge.section(document, name, key_valid, key_code, value, order)
        if entries:
            normalized[name] = entries
    if judge.issues:
        raise BindingRejection(judge.issues)
    return normalized


def _matches(pattern: re.Pattern[str]) -> Callable[[Any], bool]:
    return lambda key: pattern.fullmatch(key) is not None


_IDENTIFIER_BYTES: dict[str, int] = {"postgres": 63, "mariadb": 64}


@dataclass(frozen=True, order=True)
class PhysicalTable:
    """A relation's location components, in order, and its raw local name."""

    qualifier: tuple[str, ...]
    name: str

    def __str__(self) -> str:
        """The dotted spelling a diagnostic shows; never parsed back."""
        return ".".join((*self.qualifier, self.name))


@dataclass(frozen=True)
class Placement:
    """One model resolved under one binding: each mapping owner's table and
    each logical allocator's sequence, keyed by owner identity and allocator key."""

    dialect: str
    tables: Mapping[str, PhysicalTable]
    sequences: Mapping[str, PhysicalTable]

    def table(self, mapping_owner: str) -> PhysicalTable:
        return self.tables[mapping_owner]

    def owner_of(self, table: PhysicalTable) -> str | None:
        """The mapping owner placed at *table*, if any."""
        return next((owner for owner, held in self.tables.items() if held == table), None)

    @property
    def qualifiers(self) -> frozenset[tuple[str, ...]]:
        """Every location a table or sequence is placed in."""
        return frozenset(
            held.qualifier for held in (*self.tables.values(), *self.sequences.values())
        )


def _allocators(entity_defs: Iterable[Mapping[str, Any]]) -> list[str]:
    keys = set()
    for definition in entity_defs:
        for attribute in definition.get("attributes", []) or []:
            generation = attribute.get("pkGeneration") if isinstance(attribute, dict) else None
            if isinstance(generation, dict) and generation.get("strategy") == "sequence":
                keys.add(generation["name"])
    return sorted(keys)


def _identity(definition: Mapping[str, Any]) -> str:
    namespace = definition.get("namespace")
    return definition["name"] if namespace is None else f"{namespace}.{definition['name']}"


class _Placer:
    def __init__(self, document: Mapping[str, Any], dialect: str) -> None:
        self.document = document
        self.dialect = dialect
        self.location_key = LOCATION_KEYS[dialect]
        self.issues: set[BindingIssue] = set()

    def valid(self, components: Iterable[str], path: tuple[str, ...]) -> bool:
        ok = True
        for component in components:
            if (
                component == ""
                or "\x00" in component
                or len(component.encode("utf-8")) > _IDENTIFIER_BYTES[self.dialect]
            ):
                self.issues.add(BindingIssue(path, "binding-identifier-invalid"))
                ok = False
        return ok

    def located(
        self, entry: Mapping[str, str] | None, entry_path: tuple[str, ...], namespace: str | None
    ) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
        if entry is not None and self.location_key in entry:
            return (entry[self.location_key],), entry_path
        namespaces = self.document.get("namespaces", {})
        if namespace is not None and namespace in namespaces:
            return (namespaces[namespace][self.location_key],), ("namespaces", namespace)
        default = self.document.get("default")
        if default is not None:
            return (default[self.location_key],), ("default",)
        return None

    def place(
        self,
        key: str,
        section: str,
        name_key: str,
        default_name: str,
        namespace: str | None,
        unresolved: str,
    ) -> PhysicalTable | None:
        entry = self.document.get(section, {}).get(key)
        path = (section, key)
        located = self.located(entry, path, namespace)
        if located is None:
            self.issues.add(BindingIssue(path, unresolved))
            return None
        qualifier, location_path = located
        name = entry.get(name_key, default_name) if entry is not None else default_name
        ok = self.valid(qualifier, location_path)
        ok = self.valid((name,), (*path, name_key)) and ok
        return PhysicalTable(qualifier, name) if ok else None


def _unknown_keys(
    placer: _Placer,
    document: Mapping[str, Any],
    declared: set[str],
    owners: Mapping[str, Any],
    namespaces: set[Any],
    allocators: list[str],
) -> None:
    for owner in document.get("entities", {}):
        if owner not in declared:
            placer.issues.add(BindingIssue(("entities", owner), "binding-entity-unknown"))
        elif owner not in owners:
            placer.issues.add(BindingIssue(("entities", owner), "binding-entity-owns-no-table"))
    for namespace in document.get("namespaces", {}):
        if namespace not in namespaces:
            placer.issues.add(BindingIssue(("namespaces", namespace), "binding-namespace-unknown"))
    for allocator in document.get("sequences", {}):
        if allocator not in allocators:
            placer.issues.add(BindingIssue(("sequences", allocator), "binding-sequence-unknown"))


def _place_tables(placer: _Placer, owners: Mapping[str, Any]) -> dict[str, PhysicalTable]:
    tables: dict[str, PhysicalTable] = {}
    held: dict[PhysicalTable, str] = {}
    for owner in sorted(owners, key=_entity_order):
        namespace = owner.rpartition(".")[0] or None
        table = placer.place(
            owner, "entities", "table", owners[owner].table, namespace, "binding-table-unresolved"
        )
        if table is None:
            continue
        tables[owner] = table
        if held.setdefault(table, owner) != owner:
            placer.issues.add(BindingIssue(("entities", owner), "binding-table-collision"))
    return tables


def _place_sequences(
    placer: _Placer, allocators: list[str], tables: Mapping[str, PhysicalTable]
) -> dict[str, PhysicalTable]:
    relations = set(tables.values())
    sequences: dict[str, PhysicalTable] = {}
    held: dict[PhysicalTable, str] = {}
    for allocator in allocators:
        sequence = placer.place(
            allocator, "sequences", "sequence", allocator, None, "binding-sequence-unresolved"
        )
        if sequence is None:
            continue
        sequences[allocator] = sequence
        if held.setdefault(sequence, allocator) != allocator:
            placer.issues.add(BindingIssue(("sequences", allocator), "binding-sequence-collision"))
        if sequence in relations:
            placer.issues.add(
                BindingIssue(("sequences", allocator), "binding-sequence-table-collision")
            )
    return sequences


def resolve_binding(model: Model, document: Mapping[str, Any], dialect: str) -> Placement:
    """Place *model* under the normalized binding *document* for *dialect*.

    Raises :class:`BindingRejection` with every resolution issue m-database-binding
    names: keys naming nothing the model declares, unresolved owners and
    allocators, invalid resolved components, and physical collisions.
    """
    placer = _Placer(document, dialect)
    defs = model.entity_defs
    owners = {layout.mapping_owner: layout for layout in model.storage_layout.tables}
    allocators = _allocators(defs)
    _unknown_keys(
        placer,
        document,
        {_identity(definition) for definition in defs},
        owners,
        {definition.get("namespace") for definition in defs} - {None},
        allocators,
    )
    tables = _place_tables(placer, owners)
    sequences = _place_sequences(placer, allocators, tables)
    if placer.issues:
        raise BindingRejection(placer.issues)
    return Placement(dialect, tables, sequences)
