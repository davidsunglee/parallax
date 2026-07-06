# Transaction callbacks return values after commit

The TypeScript `transaction` API returns the callback's resolved value after the unit of work flushes and commits. If the callback throws, rejects, or commit fails, the transaction rolls back and the returned promise rejects; the `ParallaxTransaction` is not valid after the callback completes.
