# Nested transactions join the active transaction

A transaction requested while another Parallax transaction is active joins the active transaction rather than opening an independent nested database transaction. This avoids ambiguous commit ownership while preserving composability.
