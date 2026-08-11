# In-transaction read locks apply to object finds, not aggregations

Object finds through a locking transaction take the shared row lock by default, so a read-then-write is protected without the caller writing locking SQL. Aggregation reads follow `m-agg`'s separate never-locking rule. The dialect owns applying the object-find lock.
