# Processing instants come from clock strategy

Processing instants are supplied by a configured Parallax clock strategy instead of per-operation production code overrides. This centralizes the unsafe power to control processing time while still supporting tests.
