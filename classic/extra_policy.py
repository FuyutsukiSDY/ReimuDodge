"""New-edition tactics on Classic Extra only; never shrink collision geometry."""
import numpy as np
from new_routes import guidance as new_guidance
from extra_engine import plan as new_plan

def enabled(s,switch):return bool(switch and s.get('edition')=='classic' and s.get('stage')==7)

def guidance(s):
    # Shape recognition is separate from the collision arrays sent to planning.
    b=np.array(s['bullets'],float,copy=True).reshape(-1,5)
    half=np.asarray(s.get('bullet_half',[]),float)
    if half.shape==(len(b),2):b[:,4]=np.min(half,axis=1)
    lasers=[dict(l,width=l.get('render_width',l['width'])) for l in s['lasers']]
    route=new_guidance(s['player'],b,lasers,s['enemies'],s['bounds'])
    return dict(route,source='new_extra_experiment') if route else None

def choose(s,previous):
    # Original Classic player radius, circumscribed bullet radii, laser hit
    # width, enemy bodies, speed and boundaries are passed through unchanged.
    return new_plan(s['player'],s['bullets'],s['lasers'],s['speeds'],s['radius'],previous,
                    enemies=s['enemies'],bounds=s['bounds'],route_override=s.get('route'),width=12)
