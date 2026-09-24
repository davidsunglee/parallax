from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, TypedDict, cast

import yaml

from parallax.core.db_port import IsolationLevel
from parallax.core.unit_work import Concurrency, concurrency_preference
from parallax.core.wire._json import authored_number
from parallax.snapshot import DatabaseOptions

__all__ = [
    "CASE_SHAPES",
    "ActorSelection",
    "Case",
    "DatabaseLoginSelection",
    "SelectionFilter",
    "SubjectSelection",
    "TransactionKeywords",
    "actor_selection",
    "database_options",
    "default_cases_dir",
    "effective_options",
    "find_repo_root",
    "is_module_tag",
    "is_selected",
    "isolation_literal",
    "load_case",
    "load_cases",
    "request_keywords",
    "safe_load_yaml",
    "select",
    "serialized_isolation",
    "step_actor_selection",
    "transaction_keywords",
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


# The schema below lives entirely on the Python side of a load — in the
# resolver table that decides which plain scalars carry a type and in the
# constructors that decide what each one means — and both of PyYAML's parsers
# hand their scalars to those same tables. Which parser scans the text therefore
# changes what a corpus read costs and nothing about what it reads, so the
# loader takes libyaml's when the installed wheel carries it.
if TYPE_CHECKING:
    _SafeLoaderBase = yaml.SafeLoader
else:
    _SafeLoaderBase = yaml.CSafeLoader if yaml.__with_libyaml__ else yaml.SafeLoader


class _Yaml12CoreLoader(_SafeLoaderBase):
    """The safe loader whose implicit resolvers are exactly the YAML 1.2 core
    schema's four — null, boolean, integer, float — so every other plain scalar
    in a corpus document is the STRING its author wrote.

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
    return cast("int", authored_number(text))


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

# The eleven case shapes (m-case-format / conformance-adapter caseShape enum).
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
        "edit",
        "rejected",
        "evolution",
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


@dataclass(frozen=True, slots=True)
class SubjectSelection:
    """One case-authored principal selection, decoded at case ingress."""

    subject: str
    database_authorization: str


@dataclass(frozen=True, slots=True)
class DatabaseLoginSelection:
    """The explicit database-login mode, whose identity comes from the runtime."""


type ActorSelection = SubjectSelection | DatabaseLoginSelection


def actor_selection(case: Case) -> ActorSelection | None:
    """The outer boundary's authored authority, or ``None`` for the runner's
    explicit login-scope default.

    The absence is case-language interpretation only. Production still requires
    an explicit scope selection.
    """
    when = case.document.get("when")
    mapping: Mapping[str, object] = (
        cast("Mapping[str, object]", when) if isinstance(when, Mapping) else {}
    )
    if case.shape != "boundary" and _authors_actor_selection(mapping):
        raise ValueError(
            f"{case.path.name}: when authority selection is legal only for boundary cases"
        )
    return _actor_selection(mapping, where=f"{case.path.name}: when")


def step_actor_selection(step: Mapping[str, object], *, where: str) -> ActorSelection | None:
    """The independently authored authority on one joining step, or ``None``
    when that join reuses its enclosing scope."""
    if step.get("action") != "join" and _authors_actor_selection(step):
        raise ValueError(f"{where} authority selection is legal only on a join action")
    return _actor_selection(step, where=where)


def _authors_actor_selection(container: Mapping[str, object]) -> bool:
    return "actorIdentity" in container or "databaseAuthorization" in container


def _actor_selection(container: Mapping[str, object], *, where: str) -> ActorSelection | None:
    if "actorIdentity" not in container:
        if "databaseAuthorization" in container:
            raise ValueError(f"{where}.databaseAuthorization requires {where}.actorIdentity")
        return None
    actor = container["actorIdentity"]
    authorization = container.get("databaseAuthorization")
    if not isinstance(actor, Mapping):
        raise ValueError(f"{where}.actorIdentity must be a mapping, got {actor!r}")
    authored = cast("Mapping[str, object]", actor)
    unknown = sorted(set(authored) - {"kind", "value"})
    if unknown:
        raise ValueError(f"{where}.actorIdentity names unknown keys {unknown}")
    kind = authored.get("kind")
    if kind == "subject":
        if set(authored) != {"kind", "value"}:
            raise ValueError(
                f"{where}.actorIdentity subject selection requires exactly kind and value"
            )
        subject = authored["value"]
        if not isinstance(subject, str) or not subject or subject.startswith("db-login:"):
            raise ValueError(
                f"{where}.actorIdentity.value must be a nonempty, nonreserved subject string"
            )
        if not isinstance(authorization, str) or not authorization:
            raise ValueError(
                f"{where}.databaseAuthorization must be a nonempty fixture selector for a subject"
            )
        return SubjectSelection(subject, authorization)
    if kind == "database-login":
        if set(authored) != {"kind"}:
            raise ValueError(f"{where}.actorIdentity database-login selection carries no value")
        if "databaseAuthorization" in container:
            raise ValueError(
                f"{where}.databaseAuthorization is forbidden for database-login selection"
            )
        return DatabaseLoginSelection()
    raise ValueError(
        f"{where}.actorIdentity.kind must be one of ['database-login', 'subject'], got {kind!r}"
    )


_SERIALIZED_ISOLATION: Final[Mapping[IsolationLevel, str]] = {
    "read_committed": "read-committed",
    "repeatable_read": "repeatable-read",
    "serializable": "serializable",
}
"""The `m-case-format` isolation token each Python level is named by — the one
spelling every placement of the field uses (`when.uow.isolation`,
`given.databaseOptions.isolation`, a `join` step's `isolation`).

Both spellings are stated because only the right-hand side is core-authored:
recasing one into the other would make the Python identifier load-bearing for a
corpus token it does not state (`core/spec/00-overview.md` *Representation
spelling*).
"""

_ISOLATION_LITERALS: Final[Mapping[str, IsolationLevel]] = {
    serialized: level for level, serialized in _SERIALIZED_ISOLATION.items()
}


def isolation_literal(value: str) -> IsolationLevel:
    """The Python level a case's core serialized isolation token names, whichever
    placement spelled it.

    The corpus spells a level hyphenated and the language spells it as a Python
    identifier, so one projection sits at case ingress and every runner reads the
    projected value. Only the three core serialized tokens are accepted: a
    Python level's own spelling names no corpus value, so admitting it would
    alias a core-authored representation (`core/spec/00-overview.md`
    *Representation spelling*). A token outside the projection is refused here
    rather than reaching a runner as a bare string; the refusal names the
    vocabulary, and the decoder that knows the placement prefixes it.
    """
    level = _ISOLATION_LITERALS.get(value)
    if level is None:
        raise ValueError(f"isolation must be one of {sorted(_ISOLATION_LITERALS)}, got {value!r}")
    return level


def serialized_isolation(level: IsolationLevel) -> str:
    """The core serialized spelling of ``level`` — the inverse of
    :func:`isolation_literal`.

    An observation a case grades is compared against the case's own document, so
    a level leaving the language reaches that comparison spelled as the corpus
    spells it.
    """
    return _SERIALIZED_ISOLATION[level]


class TransactionKeywords(TypedDict, total=False):
    """The four option fields one option block AUTHORS, and no others.

    A sparse projection of one `when.uow` block, one `join` step, or the
    `given.databaseOptions` root block: a key is present exactly when the case
    wrote the field. Authored ``0`` and ``false`` are present values, and
    authored ``null`` is refused at ingress rather than carried. What an absent
    key means is the placement's. On `when.uow` or a `join` step the projection
    IS the ``db.transact`` request, so the omitted keyword is resolved by
    production — against the root's defaults on an outer call, against the
    active transaction on a join — never against a default restated here. On
    the root block it is the sparse input :func:`database_options` fills to a
    complete record, so the omission lands on the record's own built-in.
    """

    max_retries: int
    concurrency: Concurrency
    retry_optimistic_conflicts: bool
    isolation: IsolationLevel


_REQUEST_KEYS: Final[tuple[str, ...]] = (
    "maxRetries",
    "concurrency",
    "retryOptimisticConflicts",
    "isolation",
)


def request_keywords(request: Mapping[str, object], *, where: str) -> TransactionKeywords:
    """The option fields ``request`` authors, decoded through the case format's
    own vocabulary functions.

    ``request`` is any placement that spells the four option fields — a
    `when.uow` block, a `join` step, or the `given.databaseOptions` root block —
    and only the four option keys are read, so a step's own members travel
    beside them untouched. ``where`` names the placement every malformed field
    is reported at, a vocabulary refusal included.
    """
    keywords: TransactionKeywords = {}
    if "maxRetries" in request:
        bound = request["maxRetries"]
        if isinstance(bound, bool) or not isinstance(bound, int) or bound < 0:
            raise ValueError(f"{where}.maxRetries must be a nonnegative integer, got {bound!r}")
        keywords["max_retries"] = bound
    if "concurrency" in request:
        keywords["concurrency"] = _vocabulary_member(
            concurrency_preference, request["concurrency"], f"{where}.concurrency"
        )
    if "retryOptimisticConflicts" in request:
        opt_in = request["retryOptimisticConflicts"]
        if not isinstance(opt_in, bool):
            raise ValueError(f"{where}.retryOptimisticConflicts must be a boolean, got {opt_in!r}")
        keywords["retry_optimistic_conflicts"] = opt_in
    if "isolation" in request:
        keywords["isolation"] = _vocabulary_member(
            isolation_literal, request["isolation"], f"{where}.isolation"
        )
    return keywords


def transaction_keywords(case: Case) -> TransactionKeywords:
    """The ``db.transact`` keywords a case's `when.uow` authors for its outer
    invocation — every authored field and nothing else.

    A `when.uow` naming a key outside the four request keys is refused here, so
    a retired spelling reports the case rather than silently requesting nothing.
    """
    return _option_block_keywords(case, "when", "uow")


def database_options(case: Case) -> DatabaseOptions:
    """The record the case's Database Root is CONNECTED with: its
    `given.databaseOptions`, decoded through the same field rules a request
    meets, with every field the case omits at the record's own built-in default.

    Configuration alone, never a resolution: what an invocation runs under is
    production's to resolve from this record and the sparse request
    :func:`transaction_keywords` projects, and a lane hands each to its own seam.
    """
    return DatabaseOptions(**_option_block_keywords(case, "given", "databaseOptions"))


def effective_options(case: Case) -> DatabaseOptions:
    """The options the case's OUTER invocation resolves to — each authored
    `when.uow` field over the root record — calculated here, independently of
    production, for what a lane must know before or after the invocation runs:
    the strategy a golden is planned and graded under, the attempt count an
    oracle expects, the level a raw held session stands in at.

    Never an argument to ``db.transact`` or to ``connect``: a lane that fed this
    record into production would be testing its own arithmetic. The root record
    and the sparse request travel separately, and this is the value they meet at
    only on the grading side.
    """
    return dataclasses.replace(database_options(case), **transaction_keywords(case))


def _option_block_keywords(case: Case, group: str, member: str) -> TransactionKeywords:
    """The option fields one option block of ``case`` authors — its
    ``group.member`` mapping — refusing a key outside the four option keys."""
    container = case.document.get(group)
    block = (
        cast("Mapping[str, object]", container).get(member)
        if isinstance(container, Mapping)
        else None
    )
    if block is None:
        return {}
    where = f"{case.path.name}: {group}.{member}"
    if not isinstance(block, Mapping):
        raise ValueError(f"{where} must be a mapping, got {block!r}")
    request = cast("Mapping[str, object]", block)
    unknown = sorted(set(request) - set(_REQUEST_KEYS))
    if unknown:
        raise ValueError(
            f"{where} names no option key {unknown}; the option keys are {list(_REQUEST_KEYS)}"
        )
    return request_keywords(request, where=where)


def _authored_string(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{where} must be a string, got {value!r}")
    return value


def _vocabulary_member[T](project: Callable[[str], T], value: object, where: str) -> T:
    """``value`` projected through ``project``, a vocabulary function that names
    only the vocabulary in its refusal; the refusal is re-raised at ``where``."""
    authored = _authored_string(value, where)
    try:
        return project(authored)
    except ValueError as exc:
        raise ValueError(f"{where}: {exc}") from None


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
    """The claim projection the case-selection expression evaluates against."""

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
    """Evaluate the case-selection expression for one case.

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
