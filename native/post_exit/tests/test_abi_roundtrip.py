"""Exercise an actual compiled C function -> Python CFUNCTYPE call, no Qt claims."""
import ctypes as C
import sys
library = C.CDLL(sys.argv[1])
callback_type = C.CFUNCTYPE(C.c_int32, C.c_uint64, C.c_uint64, C.c_uint64, C.c_uint32)
library.cae_test_status_size.restype = C.c_uint32
library.cae_test_last_offset.restype = C.c_uint32
library.cae_test_roundtrip.argtypes = [callback_type]
library.cae_test_roundtrip.restype = C.c_int32
observed = []
@callback_type
def callback(client, registration, attempt, event):
    observed.append((client, registration, attempt, event))
    return -1
assert library.cae_test_status_size() == 96
assert library.cae_test_last_offset() == 88
assert library.cae_test_roundtrip(callback) == -1
assert observed == [(0x8000000000000001, 0x8000000000000002, 0x8000000000000003, 2)]
print('PASS: real C/Python cdecl callback, uint64 identifiers, UNKNOWN signed return')
