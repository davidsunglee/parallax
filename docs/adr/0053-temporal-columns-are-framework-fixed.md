# Temporal columns are framework-fixed

The four physical columns of the temporal axes — `from_z`, `thru_z`, `in_z`,
`out_z` — are fixed by the framework. They are the only names in the model
vocabulary a `column` override cannot reach.

Two specifications used to disagree about this. `m-descriptor` said the temporal
columns were ordinary Attribute `column` overrides that the axis merely never
repeated; `m-storage-layout` said "framework-fixed temporal and audit spellings
stay fixed". The Python frontend already implemented the strict reading, by
injecting the four members with fixed name-to-column pairs an author could not
redeclare, and every model in the corpus used the conventional columns. The
descriptor was the outlier, and the contradiction is resolved toward what the
implementations and the corpus already did.

Deriving the axes from the `temporality` profile settles it structurally rather
than by a new rule. The Attribute an override would sit on no longer exists in
the document: both endpoints of every axis are synthesized, each with its column
supplied from the normative mapping — deliberately not through `defaultColumn`,
which folds `txStart` to `tx_start` rather than `in_z` and so could never produce
these names. There is therefore no authored declaration on which to hang an
override, and no rejection dedicated to attempting one: authoring the Attribute
at all is `temporal-attribute-declared`, which fires on the name before a
`column` beside it is ever inspected.

What this costs is a model that wants different physical spellings for its
milestone columns. Nothing in the corpus wanted one, and the alternative — a
per-axis physical override — is precisely the repeated, unenforced convention
this change removes: the emitted Latest predicate, the close update, the
milestone oracles, and every golden SQL fragment name those columns, and each
would have to resolve them through metadata to admit a model that renamed them,
for a capability no model asked for.

Reladomo leaves these spellings authored: every `<AsOfAttribute>` carries
`fromColumnName` and `toColumnName`, so each dated object names its own
milestone columns (`docs/research/reladomo/02-object-metamodel.md:21`). Its own
tooling nevertheless assumes the convention. The reverse-engineering generator
recognizes milestone columns by the fixed name pairs `FROM_Z`/`THRU_Z` and
`IN_Z`/`OUT_Z` and emits an `<AsOfAttribute>` for those alone
(`docs/research/reladomo/24-pure-temp-objects-and-extraction.md:15`), so a table
that spelled them otherwise reverse-engineers back as two ordinary Timestamp
attributes and loses its temporality. Parallax diverges by fixing what Reladomo
authors — the same convention, with the assumption its tooling already makes
turned into a shape rather than left implicit.

Audit columns are unaffected. They are a separate designation with its own
owner; this record fixes the temporal four only.

Not chosen: keeping the columns overridable and adding a value rule that rejects
an override differing from the convention, which is the same restriction stated
as a rejection instead of as a shape, and leaves the schema admitting a document
whose only legal value is the one it would have derived.
