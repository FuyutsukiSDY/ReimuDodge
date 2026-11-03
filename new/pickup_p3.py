"""Predict a reachable falling-item intercept and validate travel plus a stop.
Only short receding-horizon commands are executed; no future spawn guarantee.
"""
import numpy as np
from engine import ACTIONS,swept
from enemies import enemy_hazards

_lock=None
_last_frame=-1
_blocked={}
def reset():
    global _lock,_last_frame
    _lock=None;_last_frame=-1;_blocked.clear()

def intercept(s,previous,baseline,enabled):
    global _lock,_last_frame
    frame=s['frame']
    if frame<_last_frame or frame-_last_frame>90:reset()
    _last_frame=frame

    info={'reason':'disabled','candidates':0,'checked':0}
    s['pickup_search']=info
    def reject(reason):
        global _lock
        if _lock is not None:_blocked[_lock['slot']]=frame+45
        _lock=None;info['reason']=reason;return None
    if not enabled:return reject('disabled')
    if s.get('power') is None or s.get('pickup_error'):return reject('unknown_power')
    if s['power']>=128:return reject('max_power')
    if s['state']!=0 or s.get('bomb_active') or s['lasers'] or baseline[2]>=1000:return reject('danger_state')
    route=s.get('route') or {};mode=route.get('mode')
    if mode not in (None,'stream'):return reject('special_route')
    p=np.asarray(s['player'],float);xmin,ymin,xmax,ymax=s['bounds']
    old=ACTIONS[previous]
    def velocity(a):
        x,y,f=ACTIONS[a];v=s['speeds'][3 if f else 2] if x and y else s['speeds'][1 if f else 0]
        return np.array([x*v,y*v])
    oldv=velocity(previous);options=[]
    early_stage=s.get('stage',(s.get('game') or {}).get('stage')) in (1,2)
    info['early_stage_priority']=early_stage
    # Focus movement is deliberately retained; wider lead time replaces rushing.
    speed=s['speeds'][1];diag=s['speeds'][3]
    items=s.get('power_items',[])
    if _lock is not None:
        matching=[it for it in items if it['slot']==_lock['slot'] and it['kind']==_lock['kind']]
        if not matching or frame-_lock['born']>90:
            _lock=None
        elif np.linalg.norm(np.array(matching[0]['pos'])-np.array(_lock['last_pos']))>48:
            _lock=None
        else:items=matching
    for item in items:
        if _blocked.get(item['slot'],-1)>frame:continue
        q=np.asarray(item['pos']);iv=np.asarray(item['velocity']);big=item['kind'] in (2,4)
        if item.get('mode',0)!=0 or not .1<=iv[1]<=6 or abs(iv[0])>2:continue
        locked=_lock is not None and item['slot']==_lock['slot']
        etas=(_lock['target'][1]-q[1],) if locked else ()
        etas=(etas[0]/iv[1],) if locked else ((12,24,36,48,60) if early_stage else (12,24,36,48))
        for eta in etas:
            if not -2<=eta<=60:continue
            eta=max(0,eta)
            target=np.array(_lock['target']) if locked else q+iv*eta
            if locked and abs(q[0]+iv[0]*eta-target[0])>8:continue
            if not xmin+20<=target[0]<=xmax-20 or not max(ymin+80,200)<=target[1]<=ymax-12:continue
            delta=target-p;dist=np.linalg.norm(delta)
            if dist>((208 if big else 176) if early_stage else (192 if big else 144)):continue
            if mode=='stream':
                # Follow the established lane; never reverse or climb for an item.
                if abs(delta[1])>24 or delta[0]*route.get('direction',0)<-6:continue
                if abs(target[1]-route['target'][1])>48:continue
                if locked and eta>12 and np.linalg.norm(delta)<6:continue
            delta[np.abs(delta)<=4]=0
            sign=np.sign(delta).astype(int);ad=np.abs(delta)
            diagonal=min(ad)/diag if min(ad)>6 else 0
            legs=[];at=p.copy();elapsed=0
            if diagonal:
                v=sign*diag;legs.append((at.copy(),v,diagonal,elapsed));at+=v*diagonal;elapsed+=diagonal
            remaining=p+delta-at;axis=int(np.argmax(abs(remaining)));duration=abs(remaining[axis])/speed
            if duration>.01:
                v=np.zeros(2);v[axis]=np.sign(remaining[axis])*speed
                legs.append((at.copy(),v,duration,elapsed));at+=v*duration;elapsed+=duration
            if elapsed>eta+2:continue
            first_v=legs[0][1] if legs else np.zeros(2)
            action=next(a for a in range(9) if np.allclose(velocity(a),first_v))
            if old[0]*ACTIONS[action][0]<0:continue
            legs.append((at.copy(),np.zeros(2),max(35,eta+12)-elapsed,elapsed))
            options.append((not big,eta+dist*.1,item,target,action,legs))
    info['candidates']=len(options)
    if not options:return reject('no_reachable_intercept')
    hazards=np.concatenate((np.asarray(s['bullets'],float).reshape(-1,5),enemy_hazards(s['enemies'])))
    def gap(at,v,dt,t):return float(swept(at[None,:],v[None,:],dt,t,hazards,[],s['radius'],1)[0])
    for _,_,item,target,action,legs in sorted(options,key=lambda o:o[:2])[:6]:
        info['checked']+=1;minimum=gap(p,oldv,2,0)
        # The next command may be held for several frames before replanning.
        for delay in (0,1,2):
            start=p+oldv*delay;end=start+velocity(action)*3
            if np.any(np.minimum(start,end)<[xmin,ymin]) or np.any(np.maximum(start,end)>[xmax,ymax]):minimum=-1;break
            minimum=min(minimum,gap(start,velocity(action),3,delay))
        for at,v,dt,t in legs:
            for delay in (0,2):
                start=at+oldv*delay;end=start+v*dt
                if np.any(np.minimum(start,end)<[xmin,ymin]) or np.any(np.maximum(start,end)>[xmax,ymax]):minimum=-1;break
                minimum=min(minimum,gap(start,v,dt,t+delay))
            if minimum<24:break
        if minimum<24:continue
        def point(t):
            for at,v,dt,start in legs:
                if t<=start+dt:return at+v*max(0,t-start)
            return target.copy()
        path=np.array([point(t) for t in (2,5,11,17,23,29,35)])
        _lock=dict(slot=item['slot'],kind=item['kind'],target=target.tolist(),last_pos=item['pos'],born=_lock['born'] if _lock else frame)
        info['reason']='locked_wait' if action==0 else 'locked_intercept' 
        return (action,path,baseline[2]),dict(active=True,reason=info['reason'],slot=item['slot'],kind=item['kind'],large=item['kind'] in (2,4),target=target.tolist(),clearance=minimum)
    return reject('travel_or_arrival_pressure')
