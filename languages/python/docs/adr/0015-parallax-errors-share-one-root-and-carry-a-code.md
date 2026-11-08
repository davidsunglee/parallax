# Parallax errors share one root and carry a code

Every exception Parallax raises descends from `ParallaxError`, which derives
from `Exception`. Its constructor takes `(code, message)`, which is exactly
`args`; `str()` renders `"{code}: {message}"`. `code` is a read-only view of
`args[0]`, so `except ParallaxError as error: error.code` is always safe, and an
error pickles from its state whatever its subclass's constructor takes.
`is_transient` answers whether a later attempt of the same work may succeed once
Parallax's own retries are spent; it is `False` unless the owner of a class
knows better from facts it already holds. Below the root stand `UsageError`
(the calling code must change), `ConflictError` (stored state another writer
changed) and `InternalError` (an invariant failed). They and `NoResultFound`
and `TooManyResultsFound` live in `parallax.core.base`, the lowest scope, so
every distribution can raise them.

An error class stays public only if an application handles it differently from
its parent, or reads fields only it has. Anything else is a `code` on a parent
and its class is deleted rather than hidden. Applications import every kept
class from `parallax.core`, except `DescriptorError`, which stays with the
descriptor ingestion that alone raises it and imports from
`parallax.descriptor`. A kept class whose reason another field carries has one
constant code and never restates that field in it.

A code is lowercase words joined by hyphens, named subject then outcome. The
parents check only that spelling. Each owner declares its vocabulary beside the
code that raises it, as a `Literal` alias plus `Final` constants, and raises the
parent with a constant, so a misspelled code is an undefined name. A runtime
frozenset of codes exists only where code tests membership. A code means one
thing wherever it is raised, and core-authored codes keep their core spelling.

A conflict names the row it hit: `ConflictError` carries the canonical Entity
name and the primary key by declared attribute name, spelled as the core
`flushFailure` observation spells them, and the raise site states whether it is
transient. A core-named error therefore surfaces as a Parallax parent class plus
a `code`; facts beyond `ConflictError`'s `entity` and `key` and a kept class's
own fields travel in the message.

Parallax errors are no longer `ValueError`, `RuntimeError`, `TypeError` or
`LookupError`. Only `UnloadedRelationshipError` keeps a builtin base,
`AttributeError`, so `hasattr` and `getattr` with a default keep treating an
unloaded relationship as absent; the cost is that a consumer treating every
`AttributeError` as "undefined" renders blank instead of failing. Plain argument
checks keep raising builtin `ValueError` and `TypeError`.

Keeping the builtin bases was rejected: a handler catching `ValueError` would
keep matching Parallax refusals by accident, and an application could not learn
the surface from one root. Publishing one union of every code was rejected: it
would make one module the author of every owner's vocabulary. Rendering a public
module path such as `parallax.core.ConflictError` was not adopted, since no
class reassigns its `__module__`.
