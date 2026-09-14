from snapshot_delivery_overhead import (
    ChildRequest,
    _child_command,  # pyright: ignore[reportPrivateUsage] - child protocol is under test
)


def test_child_command_carries_the_contract_sampling_counts() -> None:
    command = _child_command(
        ChildRequest(
            "workload",
            "live.eager.maxMs",
            17,
            warmups=5,
            measured=11,
        )
    )

    assert command[-6:] == [
        "--roots",
        "17",
        "--warmups",
        "5",
        "--measured",
        "11",
    ]
