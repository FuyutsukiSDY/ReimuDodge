"""Reserve a safe falling large-P lane before the item reaches pickup range."""
import numpy as np
from engine import ACTIONS,swept
from enemies import enemy_hazards

def choose(s,previous,baseline,enabled):
    if not enabled or s.get('power') is None or s['power']>=128 or s.get('pickup_error'):return None
    if s['state']!=0 or s.get('bomb_active') or s['lasers'] or baseline[2]>=1000:return None
    # This overlay handles pre-positioning only. Nearby pickups use the existing
    # interception planner and all authored movement retains priority.
    route=s.get('route') or {}
    if route.get('mode') not in (None,'stream'):return None
    p=np.asarray(s['player'],float);bounds=s['bounds']
    items=[it for it in s.get('power_items',[]) if it['kind'] in (2,4) and it.get('mode',0)==0
           and it['pos'][1]<p[1]-100 and abs(it['velocity'][0])<.1 and 0<=it['velocity'][1]<=4
           and bounds[0]+24<=it['pos'][0]<=bounds[2]-24]
    if not items:return None
    hazards=np.concatenate((np.asarray(s['bullets'],float).reshape(-1,5),enemy_hazards(s['enemies'])))
    def vel(a):
        x,y,f=ACTIONS[a];speed=s['speeds'][3 if f else 2] if x and y else s['speeds'][1 if f else 0]
        return np.array([x,y])*speed
    def gap(at,v,d,t):return float(swept(at[None,:],v[None,:],max(d,.001),t,hazards,[],s['radius'],1)[0])
    old=vel(previous)
    for it in sorted(items,key=lambda it:abs(it['pos'][0]-p[0]))[:3]:
        dx=it['pos'][0]-p[0]
        if route.get('mode')=='stream' and dx*route.get('direction',0)<-32:continue
        action=0 if abs(dx)<=10 else (10 if dx>0 else 9)
        v=vel(action);duration=0 if action==0 else abs(dx)/s['speeds'][0]
        if duration>70 or it['pos'][1]+it['velocity'][1]*(duration+8)>p[1]-24:continue
        end=p+v*duration;minimum=1e4
        for delay in (0,2):
            start=p+old*delay;finish=end+old*delay
            if any(not (bounds[0]+8<=q[0]<=bounds[2]-8 and bounds[1]+8<=q[1]<=bounds[3]-8) for q in (start,finish)):
                minimum=-1;break
            minimum=min(minimum,gap(start,v,duration,delay),gap(finish,np.zeros(2),max(16,35-duration),duration+delay))
        minimum=min(minimum,gap(p,old,2,0),gap(p+old*2,v,3,2))
        if minimum<(24 if route.get('mode')=='stream' else 20):continue
        exits=sum(bounds[0]+8<=end[0]+vel(a)[0]*6<=bounds[2]-8 and bounds[1]+8<=end[1]+vel(a)[1]*6<=bounds[3]-8
                  and gap(end,vel(a),6,duration)>=12 for a in range(1,9))
        if exits<2:continue
        path=np.array([p+v*min(t,duration) for t in (2,5,11,17,23,29,35)])
        return (action,path,baseline[2]),dict(active=True,reason='big_p_lane_hold' if action==0 else 'big_p_preposition',
            slot=it['slot'],kind=it['kind'],large=True,target=end.tolist(),clearance=minimum,exits=exits)
    return None
