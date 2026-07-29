module := "somewhere"

# A leading comment block whose first line the dump discards, and
# whose second line the dump would otherwise report as a description.
harness-lint:
    cd {{module}} && echo lint

[group("fast")]
[group("dbfree")]
[doc("the description the resolver reports")]
harness-format-check:
    cd {{module}} && echo format-check

[group("slow")]
[group("db")]
harness-test-db:
    cd {{module}} && echo test-db

[group("fast")]
harness-coverage-diff: harness-test-db
    cd {{module}} && echo coverage

harness-check-dbfree: harness-format-check harness-lint

[private]
_internal-show-detail:
    echo internal

core-show-language-spec language_spec:
    echo {{language_spec}}

show-gates *recipes:
    echo {{recipes}}
