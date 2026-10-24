"""The architecture reference check, on the committed pages and on scratch
workspaces carrying each resolution kind and each fault."""

from __future__ import annotations

from pathlib import Path

import pytest

import check_architecture_references as references
from python_workspace import Workspace, load_workspace
from tests.unit.tools._workspace_support import write_file, write_member, write_root

_MODULE = '''\
from __future__ import annotations

from typing import TYPE_CHECKING

import collections.abc
from dataclasses import dataclass as frozen_record

if TYPE_CHECKING:
    from typing import Sequence as Seq

LIMIT = 16
WIDTH: int = 4
type Alias = tuple[int, ...]
first, (second, *rest) = 1, (2, 3)

try:
    import tomllib as toml_reader
except ImportError:
    toml_reader = None


class Reader:
    """A class with every kind of member."""

    size: int
    shared = 0

    def read(self) -> None: ...

    @property
    def ready(self) -> bool:
        return True

    class Inner:
        def deeper(self) -> None: ...


def helper() -> None:
    nested = 1
    del nested


async def fetch() -> None: ...
'''


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    root = write_root(tmp_path, sources=("parallax-core",))
    write_member(
        tmp_path,
        "parallax-core",
        {
            "parallax/core/__init__.py": "from parallax.core.reading import Reader\n",
            "parallax/core/reading.py": _MODULE,
            "parallax/core/other.py": "class Elsewhere: ...\n",
        },
    )
    return load_workspace(root)


def _problems(tmp_path: Path, workspace: Workspace, text: str) -> list[str]:
    page = write_file(tmp_path, "docs/page.md", text)
    _count, findings = references.check([page], workspace)
    return [finding.render(tmp_path) for finding in findings]


def _resolves(workspace: Workspace, token: str) -> bool:
    return references.Resolver(workspace).problem(token) is None


def test_the_committed_architecture_pages_resolve() -> None:
    assert references.main([]) == 0


@pytest.mark.parametrize(
    "qualified",
    [
        "Reader",
        "helper",
        "fetch",
        "LIMIT",
        "WIDTH",
        "Alias",
        "first",
        "second",
        "rest",
        "collections",
        "frozen_record",
        "TYPE_CHECKING",
        "Seq",
        "toml_reader",
        "Reader.size",
        "Reader.shared",
        "Reader.read",
        "Reader.ready",
        "Reader.Inner",
        "Reader.Inner.deeper",
    ],
)
def test_each_declaration_kind_resolves(workspace: Workspace, qualified: str) -> None:
    assert _resolves(workspace, f"parallax.core.reading:{qualified}")


def test_a_package_module_resolves_through_its_init(workspace: Workspace) -> None:
    assert _resolves(workspace, "parallax.core:Reader")


def test_an_unknown_module_is_named_with_its_line(tmp_path: Path, workspace: Workspace) -> None:
    text = "Intro.\n\n- `parallax.core.missing:Reader`\n- `parallax.absent.reading:Reader`\n"

    assert _problems(tmp_path, workspace, text) == [
        "docs/page.md:3: `parallax.core.missing:Reader`: no workspace module parallax.core.missing",
        "docs/page.md:4: `parallax.absent.reading:Reader`: "
        "no workspace module parallax.absent.reading",
    ]


def test_an_unknown_top_level_name_fails(tmp_path: Path, workspace: Workspace) -> None:
    assert _problems(tmp_path, workspace, "`parallax.core.reading:Writer`\n") == [
        "docs/page.md:1: `parallax.core.reading:Writer`: "
        "parallax.core.reading binds no top-level Writer"
    ]


def test_a_local_inside_a_function_is_not_top_level(tmp_path: Path, workspace: Workspace) -> None:
    assert _problems(tmp_path, workspace, "`parallax.core.reading:nested`\n") == [
        "docs/page.md:1: `parallax.core.reading:nested`: "
        "parallax.core.reading binds no top-level nested"
    ]


def test_an_unknown_member_fails(tmp_path: Path, workspace: Workspace) -> None:
    assert _problems(tmp_path, workspace, "`parallax.core.reading:Reader.write`\n") == [
        "docs/page.md:1: `parallax.core.reading:Reader.write`: "
        "class Reader in parallax.core.reading declares no member write"
    ]


def test_a_member_of_a_non_class_fails(tmp_path: Path, workspace: Workspace) -> None:
    assert _problems(tmp_path, workspace, "`parallax.core.reading:helper.nested`\n") == [
        "docs/page.md:1: `parallax.core.reading:helper.nested`: "
        "helper in parallax.core.reading is not a class, so it declares no members"
    ]


def test_a_member_through_an_import_alias_fails(tmp_path: Path, workspace: Workspace) -> None:
    assert _problems(tmp_path, workspace, "`parallax.core:Reader.read`\n") == [
        "docs/page.md:1: `parallax.core:Reader.read`: Reader is an import alias in "
        "parallax.core; name its members at the module that defines it"
    ]


def test_a_same_named_definition_elsewhere_never_resolves(
    tmp_path: Path, workspace: Workspace
) -> None:
    assert _problems(tmp_path, workspace, "`parallax.core.reading:Elsewhere`\n") == [
        "docs/page.md:1: `parallax.core.reading:Elsewhere`: "
        "parallax.core.reading binds no top-level Elsewhere"
    ]


@pytest.mark.parametrize(
    "token",
    [
        "parallax.core.reading:",
        "parallax.core.reading:Reader.",
        "parallax.core..reading:Reader",
        "parallax.core.reading: Reader",
        "parallax.core.reading:Reader:read",
        "parallax.core.reading:1Reader",
        "parallax.:Reader",
    ],
)
def test_a_malformed_reference_fails(tmp_path: Path, workspace: Workspace, token: str) -> None:
    assert _problems(tmp_path, workspace, f"See `{token}`.\n") == [
        f"docs/page.md:1: malformed reference `{token}`: "
        "expected `parallax.<module>:<QualifiedName>`"
    ]


def test_only_deliberate_code_spans_are_references(tmp_path: Path, workspace: Workspace) -> None:
    text = (
        "Prose names `Missing`, `parallax.core.missing`, `other:Missing` and parallax.core:x.\n"
        "A double span ``parallax.core.reading:Reader`` and a wrapped one `` `x` `` count once.\n"
        "```text\n"
        "parallax.core.missing:Inside `parallax.core.missing:Fenced`\n"
        "```\n"
        "~~~~\n"
        "```\n"
        "`parallax.core.missing:StillFenced`\n"
        "~~~~\n"
        "After the fence: `parallax.core.missing:Outside`.\n"
    )
    page = write_file(tmp_path, "docs/page.md", text)

    assert [(found.line, found.token) for found in references.references(page)] == [
        (2, "parallax.core.reading:Reader"),
        (10, "parallax.core.missing:Outside"),
    ]


def test_the_check_counts_every_reference(tmp_path: Path, workspace: Workspace) -> None:
    page = write_file(
        tmp_path,
        "docs/page.md",
        "`parallax.core.reading:Reader` and `parallax.core.reading:Reader.read`\n",
    )

    assert references.check([page], workspace) == (2, [])


def test_main_reports_findings_against_named_pages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = write_file(tmp_path, "page.md", "`parallax.core.read_delivery:NoSuchName`\n")

    assert references.main([str(page)]) == 1
    error = capsys.readouterr().err
    assert "page.md:1: `parallax.core.read_delivery:NoSuchName`" in error


def test_main_refuses_an_empty_page_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(references, "PAGES", references.REPO_ROOT / "no-such-directory")

    assert references.main([]) == 1
    assert "no architecture pages" in capsys.readouterr().err
