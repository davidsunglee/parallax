# psycopg does not export its C loader base, so its layout is restated here:
# the instance fields its constructor fills and the one-entry vtable its
# Transformer dispatches every row cell through. Both builds, psycopg_binary
# and psycopg_c, compile the same declaration, so it is written once and each
# build's module declaration includes it.
cdef class CLoader:
    cdef public unsigned int oid
    cdef object _pgconn

    cdef object cload(self, const char *data, size_t length)
