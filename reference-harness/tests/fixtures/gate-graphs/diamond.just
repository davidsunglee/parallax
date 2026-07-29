[group("fast")]
leaf-check-shared:
    echo leaf

[group("medium")]
left-check-branch: leaf-check-shared
    echo left

[group("slow")]
right-check-branch: leaf-check-shared
    echo right

top-check: left-check-branch right-check-branch
