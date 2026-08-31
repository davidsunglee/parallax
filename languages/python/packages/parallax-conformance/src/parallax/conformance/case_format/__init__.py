"""``parallax.conformance.case_format`` enforcement scope (m-case-format).

Loads compatibility cases from ``core/compatibility/cases/**``, parses the
nine-shape model plus each case's tags / shape / module tags, and hosts the §1
case-selection expression (including the ``--parallax-tags`` milestone
intersection). Filename prefixes are never used for *selection* — membership is
tag-driven — but the filename does carry a case's identity (its ``<module>-NNN``
ID), per the m-case-format contract.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import yaml

from parallax.core.wire._json import authored_number

__all__ = [
    "CASE_SHAPES",
    "Case",
    "SelectionFilter",
    "default_cases_dir",
    "find_repo_root",
    "is_module_tag",
    "is_selected",
    "load_case",
    "load_cases",
    "safe_load_yaml",
    "select",
]


# The YAML 1.2 core schema's four implicit resolvers — the schema `m-case-format`
# fixes for every compatibility-corpus document — each listed with the first
# characters a matching plain scalar can start with (PyYAML's own resolver-table
# shape). The EMPTY string is one of the null resolver's entries and not a
# character at all: PyYAML looks an empty plain scalar up under the `""` bucket
# (`yaml.resolver.BaseResolver.resolve`), so `key:` resolves to null there and
# nowhere else. Spelling that entry as a character — NUL, say — registers a
# bucket no scalar ever reaches and leaves `key:` a plain string.
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


class _Yaml12CoreLoader(yaml.SafeLoader):
    """A ``yaml.SafeLoader`` whose implicit resolvers are exactly the YAML 1.2
    core schema's four — null, boolean, integer, float — so every other plain
    scalar in a corpus document is the STRING its author wrote.

    PyYAML's own default resolvers are the YAML 1.1 set, which is a different
    document language: it folds ``yes``/``no``/``on``/``off`` into booleans (so
    the ISO country code ``NO`` reads as ``False``), reads ``1_000`` and the
    sexagesimal ``1:30`` as integers, and resolves a bare ``2024-01-01`` to a
    host date object rather than to the portable ISO literal `m-document-codec`
    defines. Leaving the schema to the host library makes a corpus file's
    meaning a property of that library, which is what `m-case-format` fixes the
    schema to stop.

    Both halves are replaced. The implicit RESOLVERS decide which plain scalars
    carry a type at all; the CONSTRUCTORS decide what each resolved scalar means,
    and PyYAML's own are YAML 1.1 there too — its integer constructor reads a
    leading zero as octal, so ``017`` would be ``15`` where the core schema's
    decimal integer is ``17``, and both would still call it an integer."""


def _construct_core_int(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> int:
    """A resolved core-schema integer: decimal, or ``0o`` / ``0x`` based."""
    text = str(loader.construct_scalar(node))
    if text[:2].lower() in ("0o", "0x") or text[:3].lower() in ("-0o", "-0x", "+0o", "+0x"):
        return int(text, 0)
    return int(text, 10)


def _construct_core_float(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> float:
    """A resolved core-schema float: a decimal number, an infinity, or a NaN.

    A finite number keeps its authored digits through the production Wire
    codec's private provenance seam until a declared type is known.
    """
    text = str(loader.construct_scalar(node))
    if text.lower().lstrip("-+").startswith(".inf"):
        return float("-inf") if text.startswith("-") else float("inf")
    if text.lower().startswith(".nan"):
        return float("nan")
    return cast("float", authored_number(text))


_Yaml12CoreLoader.yaml_implicit_resolvers = {}
# Reimplements `BaseResolver.add_implicit_resolver`'s own body directly (its
# classmethod signature carries no type annotations in the `types-PyYAML`
# stub, so calling it through the class reports `reportUnknownMemberType`;
# `yaml_implicit_resolvers` itself IS typed `Any` in that same stub, so
# appending to it directly — PyYAML's own registration logic, verified
# against `yaml.resolver.BaseResolver.add_implicit_resolver`'s source — needs
# no suppression).
for _tag, _pattern, _first_chars in _CORE_SCHEMA:
    _compiled = re.compile(_pattern)
    for _first_char in _first_chars:
        _Yaml12CoreLoader.yaml_implicit_resolvers.setdefault(_first_char, []).append(
            (_tag, _compiled)
        )

_Yaml12CoreLoader.add_constructor("tag:yaml.org,2002:int", _construct_core_int)
_Yaml12CoreLoader.add_constructor("tag:yaml.org,2002:float", _construct_core_float)


def safe_load_yaml(text: str) -> object:
    """Parse one YAML document with the corpus-wide :class:`_Yaml12CoreLoader`
    (the single seam every compatibility-corpus YAML read shares — models,
    cases, and fixtures alike, see that loader's own docstring)."""
    return yaml.load(text, Loader=_Yaml12CoreLoader)


# A ``tags`` entry matching this grammar names a module (m-case-format reserved
# ``m-`` namespace); every other tag is a free-form feature or slice tag.
_MODULE_TAG = re.compile(r"^m-[a-z0-9]+(-[a-z0-9]+)*$")

# The <module>-NNN identity prefix embedded in a case filename stem.
_CASE_ID = re.compile(r"^(?P<id>m-[a-z0-9]+(?:-[a-z0-9]+)*-\d{3})-")

# The nine case shapes (m-case-format / conformance-adapter caseShape enum).
CASE_SHAPES: Final[frozenset[str]] = frozenset(
    {
        "read",
        "writeSequence",
        "scenario",
        "conflict",
        "coherence",
        "error",
        "concurrencySuccess",
        "boundary",
        "rejected",
    }
)


def is_module_tag(tag: str) -> bool:
    """Whether ``tag`` names a module (the reserved ``m-`` grammar)."""
    return _MODULE_TAG.match(tag) is not None


@dataclass(frozen=True, slots=True)
class Case:
    """A parsed compatibility case: identity, routing, and the raw document."""

    path: Path
    case_id: str
    shape: str
    tags: tuple[str, ...]
    model: str
    document: Mapping[str, object]

    @property
    def module_tags(self) -> frozenset[str]:
        """The subset of ``tags`` that name modules (the ``m-`` grammar)."""
        return frozenset(tag for tag in self.tags if is_module_tag(tag))

    @property
    def primary_module(self) -> str:
        """The first module tag — the module the case chiefly proves."""
        for tag in self.tags:
            if is_module_tag(tag):
                return tag
        raise ValueError(f"{self.path.name}: no module tag in {self.tags!r}")


def _case_id(stem: str) -> str:
    match = _CASE_ID.match(stem)
    if match is None:
        raise ValueError(f"case filename {stem!r} does not match <module>-NNN-<slug>")
    return match.group("id")


def load_case(path: Path) -> Case:
    """Parse one compatibility-case YAML file into a :class:`Case`."""
    loaded = safe_load_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.name}: case document is not a mapping")
    document = cast("dict[str, Any]", loaded)
    shape = document.get("shape")
    if not isinstance(shape, str):
        raise ValueError(f"{path.name}: missing or non-string `shape`")
    raw_tags = document.get("tags")
    if not isinstance(raw_tags, list):
        raise ValueError(f"{path.name}: missing or non-list `tags`")
    tags = tuple(str(tag) for tag in cast("list[Any]", raw_tags))
    model = str(document.get("model", ""))
    return Case(
        path=path,
        case_id=_case_id(path.stem),
        shape=shape,
        tags=tags,
        model=model,
        document=document,
    )


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (or the CWD) to the repo root holding the corpus."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "core" / "compatibility" / "cases").is_dir():
            return candidate
    raise FileNotFoundError("could not locate core/compatibility/cases above the working directory")


def default_cases_dir() -> Path:
    """The corpus case directory, discovered relative to the working directory."""
    return find_repo_root() / "core" / "compatibility" / "cases"


def load_cases(directory: Path | None = None) -> list[Case]:
    """Load every case under ``directory`` (default: the discovered corpus)."""
    root = directory if directory is not None else default_cases_dir()
    return [load_case(path) for path in sorted(root.rglob("*.yaml"))]


@dataclass(frozen=True, slots=True)
class SelectionFilter:
    """The claim projection the §1 case-selection expression evaluates against."""

    modules: frozenset[str]
    case_shapes: frozenset[str]
    include: frozenset[str]
    exclude: frozenset[str]


def is_selected(
    case: Case,
    flt: SelectionFilter,
    *,
    milestone_tags: Iterable[str] | None = None,
    implemented_modules: frozenset[str] | None = None,
) -> bool:
    """Evaluate the §1 case-selection expression for one case.

    Base membership is ``shape ∈ claimed caseShapes`` ∧ ``module-tags ⊆ claimed
    modules`` ∧ the ``caseTags`` include/exclude filters. ``milestone_tags``
    adds the ``--parallax-tags`` capability intersection (the case must carry at
    least one), and ``implemented_modules`` restricts to cases whose module tags
    are *all* implemented — the always-on reachable-intersection filter.
    """
    if case.shape not in flt.case_shapes:
        return False
    if not case.module_tags <= flt.modules:
        return False
    tag_set = set(case.tags)
    if flt.include and tag_set.isdisjoint(flt.include):
        return False
    if flt.exclude and not tag_set.isdisjoint(flt.exclude):
        return False
    if milestone_tags is not None and tag_set.isdisjoint(set(milestone_tags)):
        return False
    if implemented_modules is None:
        return True
    return case.module_tags <= implemented_modules


def select(
    cases: Iterable[Case],
    flt: SelectionFilter,
    *,
    milestone_tags: Iterable[str] | None = None,
    implemented_modules: frozenset[str] | None = None,
) -> list[Case]:
    """The subset of ``cases`` the selection expression admits (order preserved)."""
    milestone = list(milestone_tags) if milestone_tags is not None else None
    return [
        case
        for case in cases
        if is_selected(
            case,
            flt,
            milestone_tags=milestone,
            implemented_modules=implemented_modules,
        )
    ]
