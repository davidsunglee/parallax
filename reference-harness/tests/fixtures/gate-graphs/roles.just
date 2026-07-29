module := "somewhere"

# A leading comment block whose first line the dump discards, and
# whose second line the dump would otherwise report as a description.
harness-lint:
    cd {{module}} && echo lint

# `[group("slow")]` contradicts the declared runtime class on purpose: groups
# organize `just --list` and carry no classification.
[group("slow")]
[metadata("runtime:fast", "scheduling:dbfree")]
[doc("the description the resolver reports")]
harness-format-check:
    cd {{module}} && echo format-check

[metadata("runtime:slow", "scheduling:db")]
harness-test-db:
    cd {{module}} && echo test-db

[metadata("runtime:fast")]
harness-coverage-diff: harness-test-db
    cd {{module}} && echo coverage

[metadata("runtime:fast")]
[metadata("runtime:slow")]
harness-audit:
    cd {{module}} && echo audit

harness-check-dbfree: harness-format-check harness-lint

harness-check-empty:

[private]
_internal-show-detail:
    echo internal

core-show-language-spec language_spec:
    echo {{language_spec}}

show-gates *recipes:
    echo {{recipes}}
