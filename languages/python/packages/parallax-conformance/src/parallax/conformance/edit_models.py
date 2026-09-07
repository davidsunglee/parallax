"""The corpus edit model and Python's native state-carry witnesses."""

from dataclasses import dataclass
from functools import cached_property
from typing import Final, Self, cast

from pydantic import model_validator

from parallax.core import Attr, DomainModel, Entity, ValueObject, attr

__all__ = [
    "LEDGER",
    "NOTE_MODEL",
    "Note",
    "NoteMark",
    "NoteTag",
    "WitnessLedger",
    "WitnessReading",
]


@dataclass(frozen=True, slots=True)
class WitnessReading:
    hook_calls: int
    cache_evaluations: int


@dataclass(slots=True)
class WitnessLedger:
    hook_calls: int = 0
    cache_evaluations: int = 0

    def reset(self) -> None:
        self.hook_calls = 0
        self.cache_evaluations = 0

    def snapshot(self) -> WitnessReading:
        return WitnessReading(
            hook_calls=self.hook_calls,
            cache_evaluations=self.cache_evaluations,
        )


LEDGER: Final = WitnessLedger()


class NoteTag(ValueObject):
    label: Attr[str]
    weight: Attr[int | None]

    @model_validator(mode="after")
    def seed_memo(self) -> Self:
        cast("dict[str, object]", self.__dict__)["memo"] = [self.label]
        return self

    @property
    def memo(self) -> list[str]:
        return self.__dict__["memo"]

    def remember(self, payload: list[str]) -> None:
        cast("dict[str, object]", self.__dict__)["memo"] = payload

    @cached_property
    def shouted(self) -> str:
        LEDGER.cache_evaluations += 1
        return self.label.upper()


class NoteMark(ValueObject):
    kind: Attr[str]
    weight: Attr[int | None]


class Note(Entity, table="note", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    body: Attr[str | None]
    tag: Attr[NoteTag | None]
    marks: Attr[tuple[NoteMark, ...]]

    @model_validator(mode="after")
    def seed_memo(self) -> Self:
        cast("dict[str, object]", self.__dict__)["memo"] = [self.title]
        return self

    @property
    def memo(self) -> list[str]:
        return self.__dict__["memo"]

    @memo.setter
    def memo(self, payload: list[str]) -> None:
        LEDGER.hook_calls += 1
        cast("dict[str, object]", self.__dict__)["memo"] = ["intercepted"]

    def remember(self, payload: list[str]) -> None:
        cast("dict[str, object]", self.__dict__)["memo"] = payload

    @cached_property
    def shouted(self) -> str:
        LEDGER.cache_evaluations += 1
        return self.title.upper()


NOTE_MODEL = DomainModel(Note)
