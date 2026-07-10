# Deployable artifacts follow optional-dependency seams

Parallax has three related but independent topologies: the language-neutral
behavioral-module DAG, each implementation's source-enforcement graph, and its
production artifact graph. Treating a behavioral module as a package made those
topologies appear isomorphic when they answer different questions. Behavioral
modules assign normative behavior and legal dependency directions; source
enforcement scopes make those directions mechanically checkable; deployable
artifacts determine what an application must install and load.

Deployable artifacts therefore follow optional-dependency seams rather than the
behavioral-module catalog. Every language ships an independently deployable,
lifecycle-neutral common runtime. Each supported object lifecycle style ships as
a separate extension over that runtime. Each concrete database adapter ships as
a separate artifact and is the only Parallax production artifact allowed to
declare its concrete driver. The application or test composition root selects
the lifecycle extension and adapter; common runtime code below it depends on
neutral interfaces rather than concrete alternatives.

This topology keeps an application's dependency graph honest. Selecting snapshot
graphs must not install or initialize managed-object machinery, and selecting one
database must not acquire another database's driver. Development-only harnesses,
benchmarks, and container tooling likewise stay outside production runtime
graphs. A mandatory convenience artifact that pulls in every lifecycle or driver
would erase the seam and is forbidden.

The decision does not require an artifact per behavioral module. Many behavioral
modules may share a source tree and a deployable artifact when a
language-appropriate tool still enforces their dependency directions between
files, folders, namespaces, internal packages, crates, or equivalent scopes.
Pure, driver-free dialect strategies may live in the common runtime or in further
artifacts. Implementations may split the required artifacts more finely, but may
not merge the common runtime into a lifecycle extension or combine concrete
drivers into a mandatory umbrella artifact.

Reladomo is useful prior art for keeping these dimensions separate: its coarse
core runtime jar contains many internal source packages, while optional
serialization, GraphQL, XA, and other integrations ship separately, and runtime
configuration acts as its assembly point. Its internal `database/`,
`databasetype/`, and connection-manager seams also separate execution, pure
dialect decisions, and configured connectivity. Parallax adopts that semantic
separation without copying the Java layout. It makes lifecycle choice and
concrete-driver isolation explicit deployment contracts because those optional
dependencies must remain absent when unselected.

The canonical terminology and normative topology are recorded in
[`core/spec/modules.md`](../../core/spec/modules.md); the concrete adapter rules
are refined in
[`core/spec/m-db-port.md`](../../core/spec/m-db-port.md). The behavioral DAG is
unchanged by this decision: artifact boundaries neither create behavioral edges
nor make forbidden source directions legal.
