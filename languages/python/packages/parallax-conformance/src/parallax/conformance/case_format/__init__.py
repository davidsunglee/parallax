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


class _Yaml12BoolLoader(yaml.SafeLoader):
    """A ``yaml.SafeLoader`` restricted to the YAML 1.2 core schema's own
    boolean literal set (``true``/``false``, any casing) — never PyYAML's
    default YAML 1.1 resolver, which ALSO folds ``yes``/``no``/``on``/``off``
    into booleans. The corpus authors ISO country codes as bare scalars
    (``country: NO`` for Norway, ``core/compatibility/fixtures/
    customer.yaml``) — a genuine string under any modern YAML reading, but
    silently ``False`` under PyYAML's own default resolver (empirically
    confirmed): every compatibility-corpus YAML read (models/cases/fixtures)
    — the package's own loaders AND the test-side verification reads alike —
    routes through :func:`safe_load_yaml` below, so an ISO code (or any
    other bare corpus scalar) that happens to collide with the YAML 1.1
    yes/no/on/off vocabulary parses as the STRING the corpus author wrote,
    never a silently-wrong boolean."""


_Yaml12BoolLoader.yaml_implicit_resolvers = {
    first_char: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:bool"]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
# Reimplements `BaseResolver.add_implicit_resolver`'s own body directly (its
# classmethod signature carries no type annotations in the `types-PyYAML`
# stub, so calling it through the class reports `reportUnknownMemberType`;
# `yaml_implicit_resolvers` itself IS typed `Any` in that same stub, so
# appending to it directly — PyYAML's own registration logic, verified
# against `yaml.resolver.BaseResolver.add_implicit_resolver`'s source — needs
# no suppression).
for _first_char in "tTfF":
    _Yaml12BoolLoader.yaml_implicit_resolvers.setdefault(_first_char, []).append(
        ("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"))
    )


def safe_load_yaml(text: str) -> object:
    """Parse one YAML document with the corpus-wide :class:`_Yaml12BoolLoader`
    (the single seam every compatibility-corpus YAML read shares — models,
    cases, and fixtures alike, see that loader's own docstring)."""
    return yaml.load(text, Loader=_Yaml12BoolLoader)


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
