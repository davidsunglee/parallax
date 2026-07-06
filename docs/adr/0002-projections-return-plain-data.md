# Projections return plain data

Projection and aggregation queries return plain data rather than managed domain objects. This leaves room for selective attributes and grouped aggregate values without introducing partly managed entities. The boundary cuts both ways: managed objects returned from `find` are whole managed domain objects, never partially filled projections, so managed-object behavior does not depend on which attributes happened to be selected — selective attribute retrieval belongs to plain-data projection queries.
