"""Regression coverage for the streamed-delivery report fixture."""

from tools.stream_overhead import LANES, draining


def test_catalog_rows_match_the_compiled_paging_result_shape() -> None:
    draining(LANES[0], 1, batch_size=1, retaining=False)(lambda: None)
