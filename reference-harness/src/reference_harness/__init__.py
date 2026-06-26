"""The parallax M12 compatibility harness.

Tooling, not an ORM: this package never compiles operations to SQL. It validates
the compatibility suite against its JSON Schemas, normalizes and parses golden
SQL, round-trips operations and descriptors through canonical serde, boots real
databases behind the database-provider seam, and asserts that each case's golden
SQL and independent reference SQL both return the authored expected rows.
"""

__all__ = ["__version__"]
__version__ = "0.0.0"
