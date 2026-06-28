# Find does not return partial managed objects

The TypeScript `find` API returns managed domain objects and does not support selecting only a subset of attributes for those objects. Future selective retrieval should use a separate `project(...)` API that returns plain data, avoiding partially filled managed objects that would confuse identity caching, dirty tracking, and JSON serialization.
