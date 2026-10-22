"""Whether an object stays reachable from a failure's traceback frames or from
an owner, through the references those hold directly."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator
from types import FrameType, FunctionType, MethodType, ModuleType, TracebackType

__all__ = ["frames", "reaches"]


def frames(traceback: TracebackType | None, *, module: str) -> list[FrameType]:
    """Every frame of ``traceback`` running code of the file ``module``."""
    found: list[FrameType] = []
    while traceback is not None:
        frame = traceback.tb_frame
        if frame.f_code.co_filename == module:
            found.append(frame)
        traceback = traceback.tb_next
    return found


def reaches(roots: Iterable[object], target: object, *, depth: int = 4) -> bool:
    """Whether ``target`` is one of ``roots`` or is held, at most ``depth``
    references deep, by a frame's locals, a container's members, or an
    object's fields. Code, modules, and classes are not followed."""
    seen: set[int] = set()
    level = list(roots)
    for _ in range(depth + 1):
        following: list[object] = []
        for held in level:
            if held is target:
                return True
            if id(held) in seen:
                continue
            seen.add(id(held))
            following.extend(_referents(held))
        level = following
    return False


def _referents(held: object) -> Iterator[object]:
    if isinstance(held, type | ModuleType | FunctionType | MethodType):
        return
    if isinstance(held, FrameType):
        yield from held.f_locals.values()
    elif isinstance(held, dict):
        for key, value in held.items():  # pyright: ignore[reportUnknownVariableType]
            yield key
            yield value
    elif isinstance(held, list | tuple | set | frozenset | deque):
        yield from held
    else:
        yield from vars(held).values() if hasattr(held, "__dict__") else ()
        for owner in type(held).__mro__:
            slots = getattr(owner, "__slots__", ())
            for name in (slots,) if isinstance(slots, str) else slots:
                if name not in ("__dict__", "__weakref__") and hasattr(held, name):
                    yield getattr(held, name)
