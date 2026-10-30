"""Lock consistency for authored Object Query reads in scenario/coherence steps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlglot import exp
from sqlglot.expressions.core import Expr

from .case import Case, Model, load_model_metadata
from .inheritance import Family, resolve_clamped_narrow
from .references import split_reference
from .temporality import temporal_axes


class _ModelReads:
    def __init__(self, model: Model) -> None:
        self.model = model
        self.family = Family(model.entity_defs)
        self.entities = {entity.canonical_name: entity for entity in model.entities}
        self.optimistic = {
            name: bool(temporal_axes(entity.runtime_facts))
            or any(attribute.get("optimisticLocking") for attribute in entity.attributes)
            for name, entity in self.entities.items()
        }
        self.positions: dict[tuple[str, tuple[str, ...] | None], tuple[str, ...]] = {}
        self.hops: dict[tuple[str, tuple[str, ...] | None], tuple[str, ...]] = {}

    def position(self, target: str, narrow: list[str] | None) -> tuple[str, ...]:
        key = (target, None if narrow is None else tuple(narrow))
        if key not in self.positions:
            names = self.family.effective_concrete_set(target)
            if narrow is not None:
                names = resolve_clamped_narrow(self.family, names, narrow)
            self.positions[key] = tuple(self.family.defs.canonical_key(name) for name in names)
        return self.positions[key]

    def hop(self, segment: dict[str, Any]) -> tuple[str, ...]:
        reference = segment["rel"]
        narrow = segment.get("narrowTo")
        key = (reference, None if narrow is None else tuple(narrow))
        if key not in self.hops:
            owner, path = split_reference(reference)
            if owner is None or len(path) != 1:
                raise ValueError(f"unresolved include {reference!r}")
            entity = self.entities[self.family.defs.canonical_key(owner)]
            relationships = [rel for rel in entity.relationship_metadata if rel["name"] == path[0]]
            if len(relationships) != 1:
                raise ValueError(f"unresolved include {reference!r}")
            target = relationships[0]["join"]["target"]["entity"]
            self.hops[key] = self.position(target, narrow)
        return self.hops[key]

    def candidates(self, query: dict[str, Any]) -> dict[str, set[str]]:
        names = set(self.position(query["target"], query.get("narrowTo")))
        for include in query.get("includes", []):
            for segment in include["segments"]:
                names.update(self.hop(segment))
        tables: dict[str, set[str]] = {}
        for name in sorted(names):
            tables.setdefault(self.entities[name].table, set()).add(name)
        return tables


class LockConsistency:
    """Per-traversal metadata indexes for scenario/coherence read validation."""

    def __init__(self, compatibility_root: Path) -> None:
        self.root = compatibility_root
        self.models: dict[Path, _ModelReads] = {}

    def read(self, raw: dict[str, Any], step: dict[str, Any], sequence: str) -> ReadLocks | None:
        if sequence not in ("scenario", "coherence") or "objectQuery" not in step:
            return None
        # A cache hit or a refused read emits nothing for this rule to grade.
        if not step.get("statements"):
            return None
        model_rel = raw["model"]
        model_path = (self.root / model_rel).resolve()
        if model_path not in self.models:
            self.models[model_path] = _ModelReads(load_model_metadata(self.root, model_rel))
        metadata = self.models[model_path]
        preference = None
        if sequence == "scenario" and isinstance(step.get("uow"), str):
            preference = Case(Path(""), raw, metadata.model).concurrency_mode
        try:
            candidates = metadata.candidates(step["objectQuery"])
            return ReadLocks(metadata, candidates, preference)
        except (KeyError, ValueError) as exc:
            return ReadLocks(metadata, {}, preference, str(exc))


@dataclass(frozen=True)
class ReadLocks:
    metadata: _ModelReads
    candidates: dict[str, set[str]]
    preference: str | None
    mapping_error: str | None = None

    def _required(self, tree: Expr) -> tuple[bool, set[str]]:
        if self.mapping_error:
            raise ValueError(self.mapping_error)
        tables = _read_tables(tree)
        names: set[str] = set()
        for table in sorted(tables):
            matches = self.candidates.get(table, set())
            if not matches:
                raise ValueError(f"table {table!r} is outside the authored root/includes")
            # TPH variants share a canonical family position and strategy.
            roots = {self.metadata.family.root_of(name) for name in matches}
            if len(roots) != 1:
                raise ValueError(f"table {table!r} maps to competing entities {sorted(matches)}")
            names.update(matches)
        strategies = {
            self.preference is not None
            and (self.preference == "locking" or not self.metadata.optimistic[name])
            for name in names
        }
        if len(strategies) != 1:
            raise ValueError(f"incompatible strategies for {sorted(names)}")
        if len({self.metadata.family.root_of(name) for name in names}) != 1:
            raise ValueError(f"read spans unrelated entity positions {sorted(names)}")
        return strategies.pop(), tables

    def check(self, tree: Expr, text: str, dialect: str) -> str | None:
        """Return a diagnostic for the borrowed, unmodified parse tree, or None."""
        try:
            required, tables = self._required(tree)
        except ValueError as exc:
            return f"lock consistency: cannot map emitted read unambiguously: {exc}"
        locks = list(tree.find_all(exp.Lock))
        if not required:
            return (
                "lock consistency: forbidden lock on nonparticipating/optimistic read"
                if locks
                else None
            )
        suffix = {"postgres": "for share of t0", "mariadb": "lock in share mode"}[dialect]
        if not locks:
            return f"lock consistency: missing required {suffix!r}"
        expected = exp.Lock(update=False)
        if dialect == "postgres":
            expected.set("expressions", [exp.Table(this=exp.Identifier(this="t0", quoted=False))])
        if (
            len(locks) != 1
            or tree.args.get("locks") != [expected]
            or not text.endswith(" " + suffix)
        ):
            return (
                f"lock consistency: expected only outer suffix {suffix!r} "
                "(flavor, target, placement, spelling)"
            )
        if isinstance(tree, exp.Select):
            sources = _direct_tables(tree)
            if dialect == "mariadb" and len(sources) != 1:
                return "lock consistency: MariaDB shared lock must cover only the physical root"
            if not any(table.alias == "t0" and table.name in tables for table in sources):
                return "lock consistency: required lock must target the outer physical root t0"
        else:
            return "lock consistency: a UNION read cannot carry the required shared lock"
        return None


def _direct_tables(select: exp.Select) -> list[exp.Table]:
    source = select.args.get("from_")
    nodes = [source.this] if source is not None else []
    nodes.extend(join.this for join in select.args.get("joins", []))
    return [node for node in nodes if isinstance(node, exp.Table)]


def _read_tables(tree: Expr) -> set[str]:
    if isinstance(tree, exp.Subquery):
        return _read_tables(tree.this)
    if isinstance(tree, exp.Union) and not tree.args.get("distinct"):
        return _read_tables(tree.this) | _read_tables(tree.expression)
    if isinstance(tree, exp.Select):
        source = tree.args.get("from_")
        if source is not None and isinstance(source.this, exp.Table):
            return {source.this.name}
        if source is not None and isinstance(source.this, exp.Subquery):
            inner = source.this.this
            if isinstance(inner, exp.Union):
                tables = _read_tables(inner)
                joined = {table.name for table in _direct_tables(tree)}
                if joined and joined != tables:
                    raise ValueError("wrapped continuation joins a different physical root")
                return tables
    raise ValueError(f"unsupported read source {tree.key!r}")
