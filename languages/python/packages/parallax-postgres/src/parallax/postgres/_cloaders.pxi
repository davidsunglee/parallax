# The text loaders psycopg's C Transformer calls through the ``CLoader`` vtable,
# so each cell decodes straight from the driver's result buffer. The including
# module supplies ``CLoader`` and ``DriverTimestamptzLoader`` from the psycopg
# build it is compiled against.

cimport cython
from cpython.ref cimport PyObject
from libc.math cimport floor, fmod, frexp, ldexp
from libc.stdint cimport uint64_t
from libc.string cimport memcmp, memcpy

from decimal import Decimal

from psycopg.pq import Format

from parallax.core.base import FLOAT32, INFINITY, nearest_float_at_width


cdef extern from "Python.h":
    double PyOS_string_to_double(
        const char *s, char **endptr, PyObject *overflow_exception
    ) except? -1.0


cdef object _INFINITY = INFINITY
cdef object _FLOAT32 = FLOAT32


cdef inline bint _is_binary32_midpoint(double value) noexcept:
    cdef uint64_t bits
    cdef int exponent
    cdef double mantissa, halves
    # A binary32 midpoint has at most 25 significant bits, so the low 28 bits
    # of its binary64 fraction are zero. Almost every other value fails there,
    # before the exact test below.
    memcpy(&bits, &value, sizeof(bits))
    if bits & 0xFFFFFFF:
        return False
    mantissa = frexp(value, &exponent)
    halves = ldexp(mantissa, 25) if exponent > -125 else ldexp(value, 150)
    return halves == floor(halves) and fmod(halves, 2.0) != 0.0


@cython.final
cdef class ExactFloat4Loader(CLoader):
    """Decode a ``real`` cell's text to the exact binary32 value it spells.

    PostgreSQL spells a ``real`` with the shortest decimal that reads back as
    that binary32 value. Parsing it to the nearest binary64 and narrowing
    rounds twice, which differs from rounding once only where the first
    rounding lands exactly on a binary32 midpoint: midpoints are binary64
    values, so a correctly rounded parse can reach one without crossing it.
    Only there does the exact decimal decide.
    """

    format = Format.TEXT

    cdef object cload(self, const char *data, size_t length):
        cdef char *end
        cdef double parsed = PyOS_string_to_double(
            data, &end, <PyObject *>OverflowError
        )
        cdef float narrowed = <float>parsed
        if <double>narrowed == parsed:
            return parsed
        if _is_binary32_midpoint(parsed):
            return nearest_float_at_width(
                Decimal(data[:length].decode("ascii")), _FLOAT32
            )
        return <double>narrowed


@cython.final
cdef class InfinityTimestamptzLoader(CLoader):
    """Decode a ``timestamptz`` cell, reading native ``infinity`` as the
    neutral unbounded instant.

    A temporal interval's open upper bound is stored as ``infinity``, which is
    outside ``datetime``'s range, so psycopg's own loader refuses it. Every
    other cell is decoded by that loader, called through its vtable.
    """

    format = Format.TEXT

    cdef CLoader _finite

    def __cinit__(self, oid, context=None):
        self._finite = DriverTimestamptzLoader(oid, context)

    cdef object cload(self, const char *data, size_t length):
        if length == 8 and memcmp(data, b"infinity", 8) == 0:
            return _INFINITY
        return self._finite.cload(data, length)
