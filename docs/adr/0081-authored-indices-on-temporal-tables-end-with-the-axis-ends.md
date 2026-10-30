# Authored indices on temporal tables end with the axis ends

This supersedes part of [ADR 0050](0050-primary-key-index-is-derived.md) for
authored indices: its rationale for `index-temporal-attribute`, and its
principle that the Index Metadata describes exactly what is emitted. The
derived primary-key index and everything else ADR 0050 records stand.

Every authored index, unique or not, maps onto a temporal table over its
authored components followed by that table's axis end columns, Valid Time
before Transaction Time, naming a shared end once
(`m-storage-layout` *Physical indices*). This is the shape the derived primary
key already had, so every index of a temporal table now ends the same way. The
storage layout derives the ends from the family root's axes; Index Metadata,
canonical export, and model evolution keep the authored components alone
(`m-descriptor` *`index`*). An authored component naming an axis endpoint stays
refused, now because the ends are derived for every index rather than only for
the key.

Before this, an authored unique index spanned every milestone. A temporal amend
closes the current row, which keeps its unassigned values, and inserts a
successor carrying them, so an amend that kept an authored unique value was
refused by the database on both PostgreSQL and MariaDB.

On a Transaction-Time-only table, `unique (code, out_z)` admits one current row
per value and separates closed versions by their ends. It is not uniqueness at
every Transaction-Time instant: an attempt's instant may be captured before
another transaction closes a row holding the value (`m-unit-work` *The
Transaction Instant*), and a row that attempt then opens starts inside the
closed row's range while sharing neither its end nor a current row with it.

On a Bitemporal table, `unique (code, thru_z, out_z)` is uniqueness per
milestone end. An amend's head and tail slices may share the value because
their Valid-Time ends differ, and two current rows sharing the value and a
Valid-Time end are refused. Two distinct objects sharing the value over
overlapping Valid Time with different ends are not refused. This is the
guarantee Reladomo's generated DDL gives
([prior art](../research/reladomo/06-bitemporal-milestoning.md)), and the one the
primary key gives on MariaDB. `m-descriptor` states the limitation, and an
authored secondary key is not claimed to prove at most one row at a finite
as-of perspective (`m-sql` *Shared to-one joins* already requires Latest ends).

Overlap enforcement per authored unique index was measured and rejected. On
PostgreSQL, against a Bitemporal table with no authored index, one end-keyed
unique B-tree added about 10% to the database-side cost of an amend; the same
B-tree plus a current-rows GiST exclusion added about 147%, and plus a
full-history exclusion about 179%. With one commit per amend the additions were
about 4%, 12%, and 29%. The cost multiplies with every index an author declares,
and MariaDB has no exclusion at all. A read-before-write check would repeat the
database's own check and add a query to every Bitemporal write. A future opt-in
per index would be its own decision.

Physical Index Names hash the Attribute behind each column of the layout entry
(`m-schema-delta` *Physical Index Names*), so a non-temporal index keeps its
name and a temporal one takes a new name because its columns changed. Schema
Delta compares two editions compiled under the current rule and never reads the
catalog, so a database provisioned before this change keeps its authored-only
indices until an operator adopts the new shape by creating each target index
before dropping the earlier one.
