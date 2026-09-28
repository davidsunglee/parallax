# cython: language_level=3, auto_pickle=False

from psycopg_c._psycopg cimport CLoader

from psycopg_c._psycopg import TimestamptzLoader as DriverTimestamptzLoader

include "_cloaders.pxi"
