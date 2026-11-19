"""ctypes declarations for ngspice's public sharedspice.h interface."""
import ctypes as C
D, I, P, B = C.c_double, C.c_int, C.c_void_p, C.c_bool
class Value(C.Structure):
    _fields_ = [('name', C.c_char_p), ('real', D), ('imag', D), ('scale', B), ('complex', B)]
class Values(C.Structure):
    _fields_ = [('count', I), ('index', I), ('values', C.POINTER(C.POINTER(Value)))]
class Info(C.Structure):
    _fields_ = [('number', I), ('name', C.c_char_p), ('real', B), ('vector', P), ('scale', P)]
class Infos(C.Structure):
    _fields_ = [('name', C.c_char_p), ('title', C.c_char_p), ('date', C.c_char_p),
                ('type', C.c_char_p), ('count', I), ('vectors', C.POINTER(C.POINTER(Info)))]
CHAR = C.CFUNCTYPE(I, C.c_char_p, I, P)
EXIT = C.CFUNCTYPE(I, I, B, B, I, P)
DATA = C.CFUNCTYPE(I, C.POINTER(Values), I, I, P)
INIT = C.CFUNCTYPE(I, C.POINTER(Infos), I, P)
BG = C.CFUNCTYPE(I, B, I, P)
SOURCE = C.CFUNCTYPE(I, C.POINTER(D), D, C.c_char_p, I, P)
SYNC = C.CFUNCTYPE(I, D, C.POINTER(D), D, I, I, I, P)
