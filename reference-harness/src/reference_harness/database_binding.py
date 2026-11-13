"""Independent reading of m-database-binding binding documents.

A binding document is judged by a *reader* for one backend: the backend whose
location shape every section uses. :func:`normalize_binding` either returns the
document's normalized form — every empty section omitted, every map in
canonical key order — or raises :class:`BindingRejection` carrying every
definition issue as a ``(path, code)`` pair in canonical order, the way
m-database-binding defines them. Whether keys name what a model declares is a
resolution question this module does not ask.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import yaml

from .corpus_yaml import load_corpus_yaml

__all__ = [
    "LOCATION_KEYS",
    "BindingIssue",
    "BindingRejection",
    "normalize_binding",
    "parse_binding_text",
]

LOCATION_KEYS: dict[str, str] = {"postgres": "schema", "mariadb": "database"}
"""Each backend's one location key: a PostgreSQL schema, a MariaDB database."""

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
