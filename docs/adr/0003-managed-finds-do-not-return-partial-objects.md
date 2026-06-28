# Managed finds do not return partial objects

Managed objects returned from `find` represent normal managed domain objects, not partially filled projections. Selective attribute retrieval belongs to plain-data projection queries so managed-object behavior does not depend on which attributes happened to be selected.
