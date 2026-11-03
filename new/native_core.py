import ctypes as C,numpy as np,sys
from pathlib import Path
lib=C.CDLL(str(Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'core.dll'))
P=C.c_void_p;D=C.c_double;I=C.c_int;L=C.c_longlong
lib.sweep.argtypes=[I,I,P,P,P,D,D,D,D,P];lib.sweep.restype=None
lib.shot.argtypes=[L,I,C.POINTER(L),C.POINTER(L)];lib.shot.restype=I
def clearance(p,v,b,dt,now,r,margin):
    p=np.ascontiguousarray(p,dtype=np.float64).reshape(-1,2);v=np.ascontiguousarray(np.broadcast_to(v,p.shape),dtype=np.float64);b=np.ascontiguousarray(b,dtype=np.float64).reshape(-1,5);out=np.empty(len(p))
    lib.sweep(len(p),len(b),p.ctypes.data,v.ctypes.data,b.ctypes.data,dt,now,r,margin,out.ctypes.data);return out
class Shooting:
    def __init__(self):self.reset()
    def reset(self):self._p=L(-1);self._u=L(-1)
    def wanted(self,frame,enabled):return bool(lib.shot(frame,enabled,C.byref(self._p),C.byref(self._u)))
