"""Fallback pickup route search using the existing collision planner."""
import time
import numpy as np
import engine
from engine import ACTIONS,swept
from enemies import enemy_hazards

_goal=None
_frame=-1
def reset():
    global _goal,_frame
    _goal=None;_frame=-1

def intercept(s,previous,baseline,enabled):
    global _goal,_frame
    frame=s['frame']
    if frame<_frame or frame-_frame>90:reset()
    _frame=frame
    diag=s.setdefault('pickup_search',{});diag['corridor']='not_applicable'
    if (not enabled or s.get('power') is None or s['power']>=128 or s.get('pickup_error') or
        s['state']!=0 or s.get('bomb_active') or s['lasers'] or baseline[2]>=1000):
        _goal=None;return
    route=s.get('route') or {}
    if route.get('mode') not in (None,'stream'):_goal=None;return
    p=np.array(s['player'],float);lo=np.array(s['bounds'][:2]);hi=np.array(s['bounds'][2:])
    def velocity(a):
        x,y,f=ACTIONS[a];v=s['speeds'][3 if f else 2] if x and y else s['speeds'][1 if f else 0]
        return np.array([x,y])*v
    candidates=[]
    for it in s.get('power_items',[]):
        q=np.array(it['pos']);v=np.array(it['velocity'])
        if it.get('mode',0)!=0 or not .1<=v[1]<=6 or abs(v[0])>2:continue
        locked=_goal is not None and _goal['slot']==it['slot'] and _goal['kind']==it['kind'] and frame-_goal['born']<=75
        target=np.array(_goal['target']) if locked else q+v*35
        eta=(target[1]-q[1])/v[1]
        if not 3<=eta<=35 or abs(q[0]+v[0]*eta-target[0])>8:continue
        dist=np.linalg.norm(target-p)
        if dist>(200 if it['kind'] in (2,3,4) else 144):continue
        if not np.all(target>=lo+[20,0]) or not np.all(target<=hi-[20,12]) or target[1]<200:continue
        reverse=(target[0]-p[0])*ACTIONS[previous][0]<-6
        if route.get('mode')=='stream':
            if abs(target[1]-p[1])>32:continue
            reverse=reverse or (target[0]-p[0])*route.get('direction',0)<-6
        if reverse and dist>32:continue
        candidates.append((it['kind'] not in (2,3,4),not locked,dist,it,target,eta,reverse))
    if not candidates:_goal=None;diag['corridor']='no_target';return
    hazards=np.concatenate((np.asarray(s['bullets'],float).reshape(-1,5),enemy_hazards(s['enemies'])))
    oldv=velocity(previous);started=time.perf_counter()
    def gap(at,v,d,t):return float(swept(at[None,:],v[None,:],d,t,hazards,[],s['radius'],1)[0])
    def inside(p):return bool(np.all(p>=lo) and np.all(p<=hi))
    for _,_,_,it,target,eta,reverse in sorted(candidates,key=lambda x:x[:3])[:2]:
        reserve=24 if reverse else 12
        saved=dict(engine.last_search)
        try:
            result=engine.plan(p,s['bullets'],[],s['speeds'],s['radius']+reserve-1,previous,
                depth=7,width=10,enemies=s['enemies'],bounds=s['bounds'],
                route_override=dict(mode='power',target=target.tolist(),weight=.25))
        finally:engine.last_search.clear();engine.last_search.update(saved)
        if time.perf_counter()-started>.007:diag['corridor']='budget';return
        a,path,cost=result
        if cost>=1000:continue
        # Must reach the item's crossing point in time, not merely move closer.
        ts=np.array([0,2,5,11,17,23,29,35]);points=np.vstack((p,path))
        predicted=np.array([np.interp(eta,ts,points[:,j]) for j in (0,1)])
        if np.linalg.norm(predicted-target)>10:continue
        actual_reverse=ACTIONS[a][0]*ACTIONS[previous][0]<0
        if actual_reverse and not reverse:continue
        if route.get('mode')=='stream' and any((np.diff(points[:,0])*route.get('direction',0)<-1)) and not reverse:continue
        minimum=gap(p,oldv,2,0)
        for delay in (0,1,2):
            at=p+oldv*delay;end=at+velocity(a)*3
            if not inside(at) or not inside(end):minimum=-1;break
            minimum=min(minimum,gap(at,velocity(a),3,delay))
        for i in range(7):
            at=points[i];dt=ts[i+1]-ts[i];v=(points[i+1]-at)/dt
            for delay in (0,2):
                off=oldv*delay
                if not inside(at+off) or not inside(points[i+1]+off):minimum=-1;break
                minimum=min(minimum,gap(at+off,v,dt,ts[i]+delay))
        minimum=min(minimum,gap(path[-1],np.zeros(2),8,35),gap(path[-1]+oldv*2,np.zeros(2),8,37))
        if minimum<reserve:continue
        exits=sum(inside(path[-1]+velocity(k)*6) and gap(path[-1],velocity(k),6,35)>=8 for k in range(1,9))
        if exits<2:continue
        _goal=dict(slot=it['slot'],kind=it['kind'],target=target.tolist(),born=frame)
        diag['corridor']='accepted'
        return result,dict(active=True,reason='safe_pickup_corridor',slot=it['slot'],kind=it['kind'],large=it['kind'] in (2,3,4),target=target.tolist(),clearance=minimum,reverse=bool(reverse),required_clearance=reserve,exits=int(exits))
    _goal=None;diag['corridor']='no_safe_arrival'
