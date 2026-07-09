---
date: 2026-07-09
git_commit: 5e7d99ae3a1908dc658cf440acfa95de976b6ee6
topic: "Candidate ORM prior art for Parallax session-cache design"
type: research
tags: [research, orm, session-cache, unit-of-work, identity-map]
status: complete
---

# Candidate ORMs for Session-Cache Prior Art

Scope: this excludes SQLAlchemy, Hibernate, Prisma, and Reladomo as requested. Reladomo remains the local baseline for process-wide identity/query cache plus transaction integration; see `docs/research/reladomo/08-caching.md` and `docs/research/reladomo/09-transactions-locking.md`. This shortlist favors models that are useful for a Parallax slice with a session cache and no process-wide cache.

## Shortlist

| Candidate | Why it is worth considering | Primary docs/source |
|---|---|---|
| Entity Framework Core | `DbContext` is explicitly short-lived unit-of-work state; the change tracker records entity states/original values, identity resolution enforces one tracked instance per key, and no-tracking identity resolution separates result dedupe from persistence. | [DbContext lifetime](https://learn.microsoft.com/en-us/ef/core/dbcontext-configuration/), [change tracking](https://learn.microsoft.com/en-us/ef/core/change-tracking/), [identity resolution](https://learn.microsoft.com/en-us/ef/core/change-tracking/identity-resolution), [transactions](https://learn.microsoft.com/en-us/ef/core/saving/transactions), [source](https://github.com/dotnet/efcore) |
| MikroORM | A request-scoped identity map is a first-class rule: use `EntityManager.fork()` or `RequestContext`/`AsyncLocalStorage`; the global identity map is rejected by default. Its Unit of Work snapshots original values, computes changes, and ties flush to transaction boundaries. | [identity map/request context](https://mikro-orm.io/docs/identity-map), [unit of work](https://mikro-orm.io/docs/unit-of-work), [transactions](https://mikro-orm.io/docs/transactions), [entity manager](https://mikro-orm.io/docs/entity-manager), [source](https://github.com/mikro-orm/mikro-orm) |
| Doctrine ORM | `EntityManager` owns a per-request identity map and `UnitOfWork`; flush is the synchronization point and Doctrine documents transactional write-behind, clear/detach, rollback detachment, and explicit UnitOfWork internals. | [working with objects](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/working-with-objects.html), [UnitOfWork internals](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/unitofwork.html), [transactions/concurrency](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/transactions-and-concurrency.html), [second-level cache](https://www.doctrine-project.org/projects/doctrine-orm/en/current/reference/second-level-cache.html), [source](https://github.com/doctrine/orm) |
| Pony ORM | `db_session` is a decorator/context manager that defines the database conversation; each thread/session has its own identity map, session cache is cleared on exit/rollback, and optimistic checks are on by default. | [transactions and db_session](https://docs.ponyorm.org/transactions.html), [API reference](https://docs.ponyorm.org/api_reference.html), [source](https://github.com/ponyorm/pony) |
| EclipseLink | Worth a lower-priority pass for its explicit Session/UnitOfWork and identity-map APIs, plus cache-isolation concepts; less directly aligned because shared cache is central to the product model. | [documentation center](https://eclipse.dev/eclipselink/documentation/), [Javadoc](https://javadoc.io/doc/org.eclipse.persistence/eclipselink/latest/index.html), [source](https://github.com/eclipse-ee4j/eclipselink) |
| TypeORM | Useful mostly as a contrast: transaction work must use the callback-provided transactional `EntityManager`, and `QueryRunner` owns a single connection; its documented cache is query-result cache, not a session identity map. | [EntityManager](https://typeorm.io/docs/working-with-entity-manager/working-with-entity-manager/), [transactions](https://typeorm.io/docs/transactions/), [QueryRunner](https://typeorm.io/docs/query-runner/), [query caching](https://typeorm.io/docs/query-builder/caching/), [source](https://github.com/typeorm/typeorm) |

Screened but not shortlisted: NHibernate is closest to the Hibernate baseline; Rails Active Record and Django ORM look more useful as negative controls than as session-cache designs.

## Top 3 To Research Next

1. Entity Framework Core

EF Core is the strongest next target because `DbContext` maps closely to the desired Parallax boundary: a short-lived unit of work with no required process-wide object cache. Its distinctive contribution is the precise separation between tracked queries, no-tracking queries, and no-tracking queries with identity resolution. That gives Parallax a concrete model for per-session identity-map lifetime, stale tracked-object behavior when the database is queried again, attach/detach/clear semantics, and an optional read-side dedupe mode that does not enroll objects for flush.

Suggested file: `docs/research/session/01-ef-core-dbcontext-identity-resolution.md`

1. MikroORM

MikroORM is the best source for request-scope enforcement in an async runtime. Its docs explicitly treat a global identity map as a bug source, require a unique identity map per request, and route global `EntityManager` calls through `RequestContext` to a forked manager. For Parallax, this is useful prior art for making session-cache ownership explicit in APIs, preventing accidental cross-request reuse, and defining how nested transactions or transactional callbacks should clone, inherit, or clear managed objects.

Suggested file: `docs/research/session/02-mikroorm-request-context-unit-of-work.md`

1. Doctrine ORM

Doctrine is worth a focused pass because it exposes a classic but very explicit `EntityManager`/`UnitOfWork` design in a share-nothing web environment. The identity map returns the same instance for a primary key across finders and DQL within the request; `flush()` performs transactional write-behind; and error handling can close the manager and leave prior managed objects detached/out of sync. For Parallax, Doctrine is good prior art for flush ordering, identity-map clearing, rollback failure semantics, and how much UnitOfWork state should be exposed for diagnostics.

Suggested file: `docs/research/session/03-doctrine-orm-unit-of-work-identity-map.md`
