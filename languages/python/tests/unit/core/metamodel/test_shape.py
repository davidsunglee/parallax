"""m-metamodel: document-shape values and lookup."""

from parallax.core.base import STRING
from parallax.core.metamodel import Leaf, MemberShape, Multiplicity, Occurrence


def test_a_document_shape_indexes_the_same_members_as_a_linear_scan() -> None:
    first = Leaf(name="repeated", type=STRING, nullable=True)
    later = Occurrence(
        name="repeated",
        multiplicity=Multiplicity.MANY,
        nullable=False,
        shape=MemberShape(members=()),
    )
    last = Leaf(name="last", type=STRING, nullable=False)
    shape = MemberShape(members=(first, later, last))

    for name in ("repeated", "last"):
        expected = next(member for member in shape.members if member.name == name)
        assert shape.by_name.get(name) is expected
        assert shape.member(name) is expected
    assert len(shape.by_name) == 2
    assert shape.member("absent") is None
