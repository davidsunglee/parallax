"""The one YAML reader every compatibility-corpus read goes through.

`m-case-format` fixes the corpus's YAML schema at **YAML 1.2 core**, so a corpus
document's plain scalars resolve to exactly four implicit types — null, boolean,
integer, float — and every other plain scalar is a string. Reading a corpus file
with a host library's own default resolver instead makes the file's meaning a
property of that library: PyYAML resolves the YAML 1.1 types, which additionally
fold ``yes``/``no``/``on``/``off`` into booleans, read ``1_000`` and ``1:30`` as
integers, and turn a bare ``2024-01-01`` into a host date object. Two graders
reading one corpus through two host defaults grade two different documents.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

# The YAML 1.2 core schema's four implicit resolvers, keyed by the first character
# a matching plain scalar can start with (PyYAML's own resolver-table shape).
_CORE_SCHEMA: tuple[tuple[str, str, str], ...] = (
    ("tag:yaml.org,2002:null", r"^(?:null|Null|NULL|~|)$", "~nN\0"),
    ("tag:yaml.org,2002:bool", r"^(?:true|True|TRUE|false|False|FALSE)$", "tTfF"),
    ("tag:yaml.org,2002:int", r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$", "-+0123456789"),
    (
        "tag:yaml.org,2002:float",
        r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
        r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$",
        "-+0123456789.",
    ),
)


class _CoreSchemaLoader(yaml.SafeLoader):
    """A ``SafeLoader`` reading the YAML 1.2 core schema.

    Both halves are replaced. The implicit RESOLVERS decide which plain scalars
    carry a type at all; the CONSTRUCTORS decide what each resolved scalar means,
    and PyYAML's own are YAML 1.1 there too — its integer constructor reads a
    leading zero as octal, so ``017`` would be ``15`` where the core schema's
    decimal integer is ``17``, and both would still call it an integer.
    """


def _construct_core_int(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> int:
    """A resolved core-schema integer: decimal, or ``0o`` / ``0x`` based."""
    text = str(loader.construct_scalar(node))
    if text[:2].lower() in ("0o", "0x") or text[:3].lower() in ("-0o", "-0x", "+0o", "+0x"):
        return int(text, 0)
    return int(text, 10)


def _construct_core_float(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> float:
    """A resolved core-schema float: a decimal number, an infinity, or a NaN."""
    text = str(loader.construct_scalar(node))
    if text.lower().lstrip("-+").startswith(".inf"):
        return float("-inf") if text.startswith("-") else float("inf")
    if text.lower().startswith(".nan"):
        return float("nan")
    return float(text)


_CoreSchemaLoader.yaml_implicit_resolvers = {}
for _tag, _pattern, _first_characters in _CORE_SCHEMA:
    _compiled = re.compile(_pattern)
    for _first in _first_characters:
        _CoreSchemaLoader.yaml_implicit_resolvers.setdefault(_first, []).append((_tag, _compiled))

_CoreSchemaLoader.add_constructor("tag:yaml.org,2002:int", _construct_core_int)
_CoreSchemaLoader.add_constructor("tag:yaml.org,2002:float", _construct_core_float)


def load_corpus_yaml(text: str) -> Any:
    """Parse one corpus YAML document under the core schema."""
    return yaml.load(text, Loader=_CoreSchemaLoader)


def read_corpus_yaml(path: Path) -> Any:
    """Parse the corpus YAML document at *path* under the core schema."""
    return load_corpus_yaml(path.read_text(encoding="utf-8"))
