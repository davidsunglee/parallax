# A boundary case names only the actions cases perform

The `when.boundary` action vocabulary of `m-case-format` is now `read`, `amend`, and
`join`. `create`, `terminate`, and `delete` leave it, from the spec's field table and
the case schema's closed enum alike.

No boundary case authored any of the three. A boundary case exists to prove the
unit-of-work retry loop and its option rules, and every observable it states rides
on reading the target row, changing it, and joining the transaction. Keeping the
other three meant every binding's API Conformance Suite had to map each one to a
verb no case exercises, and could test that mapping only against itself: Python
inserted a synthetic account, deleted the last-read one, and refused `terminate`
outright because no boundary target declared one.

We considered keeping them as reserved vocabulary for future cases. We decided
against it for the same reason as
[ADR 0091](0091-an-as-of-axis-has-no-alteration.md): vocabulary no input uses still
costs every binding code and tests that check nothing about Parallax. A future case
that needs one of these actions adds it back together with the case that authors it.
