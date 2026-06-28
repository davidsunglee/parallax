# Generated TypeScript API exports a parallax factory

The generated TypeScript API exports a `parallax(...)` factory that creates the configured `Parallax` handle for that generated model. Application code conventionally stores the result in a local `px` variable. The generated factory keeps bootstrap code compact and idiomatic while the exported type is the domain name itself: `Parallax`.

The `Parallax` handle is not a raw database connection. It is the application-side handle that binds a generated metamodel, database adapter, clock strategy, read API, transaction API, and per-operation runtime behavior behind one entry point.
