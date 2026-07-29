core-check-schemas:
    echo schemas

[group("medium")]
core-check-module-graph:
    echo module-graph

core-check-undeclared: core-check-schemas

core-check: core-check-undeclared core-check-module-graph
