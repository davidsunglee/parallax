"""Canonical Entity spelling gate for the compatibility corpus::

    uv run python -m reference_harness.canonical_spelling_check <compatibility-dir>

Input is permissive and output is exact (`m-metamodel`): a bare Entity spelling
remains legal wherever it resolves unambiguously, but everything the corpus
SHIPS is canonical, so a reference the model resolves must be spelled exactly as
the Entity it resolves to. This gate owns that fixed point across the four
surfaces that address a model identity — cases, shared models, fixtures, and
benchmark datasets — and reports the file, the document path, the spelling it
expected, and the spelling it found.

The one semantic exception is per-reference and never per-file: a bare spelling
that two or more Entities of the model share resolves to no Entity at all, and a
case pinning `reference-ambiguous-entity-name` needs exactly such a spelling to
be ambiguous. Every OTHER reference in that same case still has to be canonical.

Like its sibling guards this raw-parses each document and builds its own
declaration index rather than reaching for the resolved corpus graph: a gate
whose job is to report a malformed document must not crash on one.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .corpus_yaml import read_corpus_yaml
from .operation_references import ATTRIBUTE_REFERENCE_TAGS, PATH_REFERENCE_TAGS
from .references import split_reference

__all__ = ["check", "main"]

_AMBIGUOUS_REFERENCE_RULE = "reference-ambiguous-entity-name"

# Every member carrying a nested predicate: a boolean combinator's or a
# Predicate-scoped narrow's `operand`, a navigation's `op`, and an element
# scope's `where`. A carrier adds no reference of its own, so one table serves
# all of them.
_OPERAND_MEMBERS = ("operand", "op", "where")


@dataclass(frozen=True, slots=True)
class _Declarations:
    """The Entity identities one model declares, indexed for reference resolution.

    Two questions, two indexes, exactly as `m-metamodel` states the reference
    rule: an exact canonical spelling names its Entity outright, and a bare local
    name names one only when the whole model declares it once.
    """

    canonical: frozenset[str]
    by_local: Mapping[str, tuple[str, ...]]

    def resolve(self, spelling: str) -> str | None:
        """The canonical spelling ``spelling`` names, or ``None`` for a spelling
        that names no declared Entity or more than one."""
        if spelling in self.canonical:
            return spelling
        matches = self.by_local.get(spelling, ())
        return matches[0] if len(matches) == 1 else None

    def candidates(self, spelling: str) -> tuple[str, ...]:
        """Every canonical spelling a bare ``spelling`` could name — non-empty
        with two or more entries exactly when the spelling is ambiguous."""
        return () if spelling in self.canonical else self.by_local.get(spelling, ())


def _identity(definition: Mapping[str, Any]) -> str | None:
    name = definition.get("name")
    if not isinstance(name, str):
        return None
    namespace = definition.get("namespace")
    return f"{namespace}.{name}" if isinstance(namespace, str) else name


def _declarations(document: Any) -> _Declarations:
    """The declaration index of one raw ``models/*.yaml`` document."""
    definitions: list[Any] = []
    if isinstance(document, Mapping):
        entities = document.get("entities")
        if isinstance(entities, Sequence) and not isinstance(entities, str):
            definitions.extend(entities)
        single = document.get("entity")
        if isinstance(single, Mapping):
            definitions.append(single)
    canonical: set[str] = set()
    by_local: dict[str, list[str]] = {}
    for definition in definitions:
        if not isinstance(definition, Mapping):
            continue
        identity = _identity(definition)
        if identity is None:
            continue
        canonical.add(identity)
        by_local.setdefault(str(definition["name"]), []).append(identity)
    return _Declarations(
        canonical=frozenset(canonical),
        by_local={local: tuple(sorted(names)) for local, names in by_local.items()},
    )


@dataclass(slots=True)
class _Report:
    """The findings collected while walking ONE document.

    ``ambiguity_expected`` is the case's own ``then.rejectedRule``, read once and
    applied per reference: it excuses an ambiguous bare spelling and nothing else.
    """

    path: Path
    ambiguity_expected: bool = False
    findings: list[str] = field(default_factory=list)

    def not_canonical(self, where: str, expected: str, found: str) -> None:
        """One reference whose Entity resolves but is not spelled as it resolves."""
        self.findings.append(f"{self.path}: {where}: expected {expected!r}, found {found!r}")

    def ambiguous(self, where: str, candidates: Sequence[str], found: str) -> None:
        """One bare reference two or more declared Entities answer to, outside the
        one case that needs an ambiguous spelling to be ambiguous."""
        expected = " or ".join(repr(candidate) for candidate in candidates)
        self.findings.append(f"{self.path}: {where}: expected {expected}, found {found!r}")

    def entity(self, spelling: Any, where: str, declarations: _Declarations) -> None:
        """Check a bare-or-canonical Entity spelling (a query ``target``, a
        ``narrow``'s ``to`` entry, or a write instruction's Entity)."""
        if not isinstance(spelling, str):
            return
        self._check(spelling, spelling, (), where, declarations)

    def member(self, reference: Any, where: str, declarations: _Declarations) -> None:
        """Check the Entity spelling of a member reference (an ``attr``, a
        ``rel``, or a value-object ``path``). An element-relative path names no
        Entity and is answered by its own resolver, never here."""
        if not isinstance(reference, str):
            return
        named, members = split_reference(reference)
        if named is None:
            return
        self._check(reference, named, members, where, declarations)

    def _check(
        self,
        reference: str,
        named: str,
        members: tuple[str, ...],
        where: str,
        declarations: _Declarations,
    ) -> None:
        resolved = declarations.resolve(named)
        if resolved is None:
            candidates = declarations.candidates(named)
            if len(candidates) > 1 and not self.ambiguity_expected:
                self.ambiguous(
                    where, [".".join((candidate, *members)) for candidate in candidates], reference
                )
            # A spelling no Entity answers to has no canonical form to demand;
            # whether that is itself a defect is the resolving validators' call.
            return
        if resolved != named:
            self.not_canonical(where, ".".join((resolved, *members)), reference)


# --------------------------------------------------------------------------- #
# The predicate / query walks: every reference position, with its path.        #
# --------------------------------------------------------------------------- #
def _walk_predicate(node: Any, where: str, report: _Report, declarations: _Declarations) -> None:
    if not isinstance(node, Mapping) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    at = f"{where}.{tag}"
    if not isinstance(body, Mapping):
        return
    if tag in ATTRIBUTE_REFERENCE_TAGS:
        report.member(body.get("attr"), f"{at}.attr", declarations)
    elif tag in PATH_REFERENCE_TAGS:
        report.member(body.get("path"), f"{at}.path", declarations)
    elif tag in ("navigate", "exists", "notExists"):
        report.member(body.get("rel"), f"{at}.rel", declarations)
    elif tag in ("and", "or"):
        for index, operand in enumerate(_items(body.get("operands"))):
            _walk_predicate(operand, f"{at}.operands[{index}]", report, declarations)
    elif tag == "narrow":
        _walk_selection(body.get("to"), f"{at}.to", report, declarations)
    for member in _OPERAND_MEMBERS:
        if member in body:
            _walk_predicate(body[member], f"{at}.{member}", report, declarations)


def _walk_selection(selection: Any, at: str, report: _Report, declarations: _Declarations) -> None:
    for index, name in enumerate(_items(selection)):
        report.entity(name, f"{at}[{index}]", declarations)


def _walk_query(node: Any, where: str, report: _Report, declarations: _Declarations) -> None:
    """Every reference position one Object Query carries, with its path."""
    if not isinstance(node, Mapping):
        return
    report.entity(node.get("target"), f"{where}.target", declarations)
    _walk_predicate(node.get("predicate"), f"{where}.predicate", report, declarations)
    _walk_selection(node.get("narrowTo"), f"{where}.narrowTo", report, declarations)
    for index, key in enumerate(_items(node.get("orderBy"))):
        if isinstance(key, Mapping):
            report.member(key.get("attr"), f"{where}.orderBy[{index}].attr", declarations)
    for index, path in enumerate(_items(node.get("includes"))):
        if not isinstance(path, Mapping):
            continue
        here = f"{where}.includes[{index}]"
        _walk_selection(path.get("appliesTo"), f"{here}.appliesTo", report, declarations)
        for position, segment in enumerate(_items(path.get("segments"))):
            spot = f"{here}.segments[{position}]"
            if not isinstance(segment, Mapping):
                report.member(segment, f"{spot}.rel", declarations)
                continue
            report.member(segment.get("rel"), f"{spot}.rel", declarations)
            _walk_selection(segment.get("narrowTo"), f"{spot}.narrowTo", report, declarations)


def _items(node: Any) -> Iterator[Any]:
    if isinstance(node, Sequence) and not isinstance(node, str):
        yield from node


# --------------------------------------------------------------------------- #
# The case walk (m-case-format): routing, queries, and write instructions.    #
# --------------------------------------------------------------------------- #
def _walk_case(document: Any, report: _Report, declarations: _Declarations) -> None:
    if not isinstance(document, Mapping):
        return
    when = document.get("when")
    if not isinstance(when, Mapping):
        return
    # An inline `when.model` case declares its OWN entities and carries no other
    # `when` member; its spellings are the authored negative and never move.
    if "model" in when:
        return
    _walk_query(when.get("objectQuery"), "when.objectQuery", report, declarations)
    for index, encoding in enumerate(_items(when.get("equivalentEncodings"))):
        _walk_query(encoding, f"when.equivalentEncodings[{index}]", report, declarations)
    _walk_write(when.get("write"), "when.write", report, declarations)
    for index, instruction in enumerate(_items(when.get("writeSequence"))):
        _walk_keyed_write(instruction, f"when.writeSequence[{index}]", report, declarations)
    for index, step in enumerate(_items(when.get("scenario"))):
        if not isinstance(step, Mapping):
            continue
        at = f"when.scenario[{index}]"
        _walk_query(step.get("objectQuery"), f"{at}.objectQuery", report, declarations)
        for encoding_index, encoding in enumerate(_items(step.get("equivalentEncodings"))):
            _walk_query(
                encoding,
                f"{at}.equivalentEncodings[{encoding_index}]",
                report,
                declarations,
            )
        _walk_write(step.get("write"), f"{at}.write", report, declarations)
    for index, step in enumerate(_items(when.get("coherence"))):
        if not isinstance(step, Mapping):
            continue
        at = f"when.coherence[{index}]"
        _walk_query(step.get("objectQuery"), f"{at}.objectQuery", report, declarations)


def _walk_write(node: Any, at: str, report: _Report, declarations: _Declarations) -> None:
    """A write step, in each of the shapes `m-case-format` gives it.

    A buffered sequence is a list of keyed instructions; a single instruction is
    keyed when it names an `entity` and predicate-selected when it names a
    `target`. A bare row (a label or a plain row object) names no Entity — the
    model's default write root answers for it — and contributes nothing.
    """
    if isinstance(node, Sequence) and not isinstance(node, str):
        for index, instruction in enumerate(node):
            _walk_keyed_write(instruction, f"{at}[{index}]", report, declarations)
        return
    if not isinstance(node, Mapping):
        return
    if "entity" in node:
        _walk_keyed_write(node, at, report, declarations)
        return
    target = node.get("target")
    if isinstance(target, Mapping):
        report.entity(target.get("entity"), f"{at}.target.entity", declarations)
        _walk_predicate(target.get("predicate"), f"{at}.target.predicate", report, declarations)
    for index, assignment in enumerate(_items(node.get("assignments"))):
        if isinstance(assignment, Mapping):
            report.member(assignment.get("attr"), f"{at}.assignments[{index}].attr", declarations)


def _walk_keyed_write(node: Any, at: str, report: _Report, declarations: _Declarations) -> None:
    if isinstance(node, Mapping):
        report.entity(node.get("entity"), f"{at}.entity", declarations)


# --------------------------------------------------------------------------- #
# The declaration-site walk (m-descriptor): a shared model's own references.   #
# --------------------------------------------------------------------------- #
def _walk_model(document: Any, report: _Report) -> None:
    """A model's inheritance parents, join targets, and reverse peers.

    These are DECLARATION sites, so the rule is the lexical one: a bare spelling
    adopts the declaring Entity's own namespace rather than being searched for
    model-wide. What the corpus ships is the resolved identity either way.
    """
    if not isinstance(document, Mapping):
        return
    definitions: list[Any] = list(_items(document.get("entities")))
    single = document.get("entity")
    if isinstance(single, Mapping):
        definitions.append(single)
    for index, definition in enumerate(definitions):
        if not isinstance(definition, Mapping):
            continue
        at = f"entity[{index}]" if "entities" in document else "entity"
        namespace = definition.get("namespace")
        owner = namespace if isinstance(namespace, str) else None
        inheritance = definition.get("inheritance")
        if isinstance(inheritance, Mapping):
            _declaration_reference(
                inheritance.get("parent"), f"{at}.inheritance.parent", owner, report
            )
        for position, relationship in enumerate(_items(definition.get("relationships"))):
            if not isinstance(relationship, Mapping):
                continue
            spot = f"{at}.relationships[{position}]"
            join = relationship.get("join")
            if isinstance(join, Mapping):
                target = join.get("target")
                if isinstance(target, Mapping):
                    _declaration_reference(
                        target.get("entity"), f"{spot}.join.target.entity", owner, report
                    )
            reverse_of = relationship.get("reverseOf")
            if isinstance(reverse_of, str):
                peer, _, member = reverse_of.rpartition(".")
                _declaration_reference(peer, f"{spot}.reverseOf", owner, report, suffix=(member,))


def _declaration_reference(
    spelling: Any,
    where: str,
    owner: str | None,
    report: _Report,
    *,
    suffix: tuple[str, ...] = (),
) -> None:
    if not isinstance(spelling, str) or not spelling:
        return
    resolved = spelling if "." in spelling or owner is None else f"{owner}.{spelling}"
    if resolved != spelling:
        report.not_canonical(where, ".".join((resolved, *suffix)), ".".join((spelling, *suffix)))


# --------------------------------------------------------------------------- #
# The gate.                                                                    #
# --------------------------------------------------------------------------- #
def check(root: Path) -> list[str]:
    """Every canonical-spelling finding across ``root``'s cases, models,
    fixtures, and benchmarks — empty when the whole corpus is canonical."""
    findings: list[str] = []
    models: dict[str, _Declarations] = {}
    for path in sorted((root / "models").glob("*.yaml")):
        document, error = _read(path)
        if error is not None:
            findings.append(error)
            continue
        models[f"models/{path.name}"] = _declarations(document)
        report = _Report(path=path)
        _walk_model(document, report)
        findings.extend(report.findings)

    for path in sorted((root / "fixtures").glob("*.yaml")):
        document, error = _read(path)
        if error is not None:
            findings.append(error)
            continue
        declarations = models.get(f"models/{path.name}")
        if declarations is None:
            findings.append(f"{path}: <root>: no models/{path.name} declares these rows")
            continue
        findings.extend(_fixture_findings(path, document, declarations, "<root>"))

    for path in sorted((root / "benchmarks").glob("*.yaml")):
        document, error = _read(path)
        if error is not None:
            findings.append(error)
            continue
        findings.extend(_benchmark_findings(path, document, models))

    for path in sorted((root / "cases").glob("*.yaml")):
        document, error = _read(path)
        if error is not None:
            findings.append(error)
            continue
        declarations = _case_declarations(path, document, models, findings)
        if declarations is None:
            continue
        report = _Report(path=path, ambiguity_expected=_expects_ambiguity(document))
        _walk_case(document, report, declarations)
        findings.extend(report.findings)
    return findings


def _read(path: Path) -> tuple[Any, str | None]:
    try:
        return read_corpus_yaml(path), None
    except Exception as error:  # noqa: BLE001 - a malformed document is a finding, not a crash
        return None, f"{path}: <root>: unreadable document ({error.__class__.__name__}: {error})"


def _case_declarations(
    path: Path,
    document: Any,
    models: Mapping[str, _Declarations],
    findings: list[str],
) -> _Declarations | None:
    if not isinstance(document, Mapping):
        findings.append(f"{path}: <root>: case document is not a mapping")
        return None
    reference = document.get("model")
    if not isinstance(reference, str):
        findings.append(f"{path}: model: case names no model")
        return None
    declarations = models.get(reference)
    if declarations is None:
        findings.append(f"{path}: model: {reference!r} is not a shared model of this corpus")
        return None
    return declarations


def _expects_ambiguity(document: Mapping[str, Any]) -> bool:
    then = document.get("then")
    return isinstance(then, Mapping) and then.get("rejectedRule") == _AMBIGUOUS_REFERENCE_RULE


def _fixture_findings(
    path: Path, document: Any, declarations: _Declarations, where: str
) -> list[str]:
    """Fixture / dataset row keys name the Entity that owns the rows."""
    if not isinstance(document, Mapping):
        return []
    report = _Report(path=path)
    for key in document:
        report.entity(key, where, declarations)
    return report.findings


def _benchmark_findings(
    path: Path, document: Any, models: Mapping[str, _Declarations]
) -> list[str]:
    if not isinstance(document, Mapping):
        return []
    reference = document.get("model")
    declarations = models.get(reference) if isinstance(reference, str) else None
    if declarations is None:
        return [f"{path}: model: {reference!r} is not a shared model of this corpus"]
    dataset = document.get("dataset")
    if not isinstance(dataset, Mapping):
        return []
    return _fixture_findings(path, dataset.get("rows"), declarations, "dataset.rows")


def main(argv: Sequence[str]) -> int:
    """CLI entry point: check every canonical Entity spelling under *argv[0]*.

    Exit codes: 0 — every shipped spelling equals its resolved identity; 1 — at
    least one spelling does not; 2 — usage error, or *argv[0]* is not a
    compatibility directory.
    """
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.canonical_spelling_check <compatibility-dir>",
            file=sys.stderr,
        )
        return 2
    root = Path(argv[0])
    if not (root / "cases").is_dir() or not (root / "models").is_dir():
        print(f"not a compatibility directory: {root}", file=sys.stderr)
        return 2

    findings = check(root)
    if findings:
        print(
            f"canonical Entity spelling check FAILED ({len(findings)} problem(s)):",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print("canonical Entity spelling check OK: every corpus Entity spelling is canonical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
