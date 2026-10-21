from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from parallax.conformance.case_format import Case
from tests._support import case_corpus


def test_corpus_parsing_is_shared_but_nested_documents_are_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads: list[None] = []

    def load() -> list[Case]:
        reads.append(None)
        return [
            Case(
                path=Path("m-core-999.yaml"),
                case_id="m-core-999",
                shape="read",
                tags=("m-core", "slice-snapshot-1"),
                model="models/orders.yaml",
                document={"when": {"rows": [{"id": 1}]}},
            )
        ]

    case_corpus._by_id.cache_clear()  # pyright: ignore[reportPrivateUsage] - isolate the process cache from the synthetic corpus
    case_corpus._reachable_ids.cache_clear()  # pyright: ignore[reportPrivateUsage] - isolate the process cache from the synthetic corpus
    monkeypatch.setattr(case_corpus.case_format, "load_cases", load)
    try:
        first = case_corpus.case("m-core-999")
        document = cast("dict[str, Any]", first.document)
        document["when"]["rows"][0]["id"] = 2
        assert case_corpus.cases()[0].document == {"when": {"rows": [{"id": 1}]}}
        assert case_corpus.case("m-core-999").document == {"when": {"rows": [{"id": 1}]}}
        reachable = case_corpus.reachable_cases()
        assert [case.case_id for case in reachable] == ["m-core-999"]
        cast("dict[str, Any]", reachable[0].document)["when"]["rows"].clear()
        assert case_corpus.case("m-core-999", reachable=True).document == {
            "when": {"rows": [{"id": 1}]}
        }
        assert reads == [None]
        with pytest.raises(KeyError, match="missing"):
            case_corpus.case("missing", reachable=True)
    finally:
        case_corpus._by_id.cache_clear()  # pyright: ignore[reportPrivateUsage] - isolate the process cache from the synthetic corpus
        case_corpus._reachable_ids.cache_clear()  # pyright: ignore[reportPrivateUsage] - isolate the process cache from the synthetic corpus
