"""Broaden short-horizon search only for observed fast large-bullet volleys."""
import numpy as np
from static_lasers import stationary

def search_width(s):
    if s.get('route'):return 12
    if s['lasers']:return 20 if all(stationary(l) for l in s['lasers']) else 12
    if len(s['enemies'])!=1:return 12
    b=np.asarray(s['bullets'],float).reshape(-1,5)
    if len(b)<24:return 12
    speed=np.linalg.norm(b[:,2:4],axis=1)
    fast_large=(np.abs(b[:,4]-16)<.01)&(np.abs(speed-6.8)<.08)
    return 20 if np.count_nonzero(fast_large)>=2 else 12
