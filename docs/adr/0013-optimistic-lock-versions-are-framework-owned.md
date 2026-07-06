# Optimistic-lock version values are framework-owned

Parallax sources optimistic-lock version values from the row the unit of work observed and computes the advanced version itself. Callers never supply a raw version number; "caller-driven" refers only to conflict handling. Updating a versioned row the unit of work never observed is a read-before-write error, and a versioned update that changes no attribute issues no DML. The normative detail lives in `core/spec/m-opt-lock.md` §Version values are framework-owned.
