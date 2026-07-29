[metadata("runtime:fast")]
leaf-check-shared:
    echo leaf

[metadata("runtime:medium")]
left-check-branch: leaf-check-shared
    echo left

[metadata("runtime:slow")]
right-check-branch: leaf-check-shared
    echo right

top-check: left-check-branch right-check-branch
