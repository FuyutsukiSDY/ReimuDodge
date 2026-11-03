"""Low-field lateral intercept for a falling P; no upward pursuit."""
import numpy as np
from enemies import enemy_hazards
from engine import ACTIONS,swept
def intercept(s,previous,baseline,enabled):
    if not enabled or not s.get('power_items') or s.get('power') is None or s['power']>=128 or s.get('pickup_error') or s['state']!=0 or s.get('bomb_active') or s['lasers'] or baseline[2]>=1000:return
    route=s.get('route') or {};mode=route.get('mode')
    if mode not in (None,'stream'):return
    p=np.array(s['player'],float);lo,top,hi,bottom=s['bounds']
    if p[1]<bottom-150:return
    speed=s['speeds'][1];opts=[]
    if speed<=0:return
    for it in s['power_items']:
        x,y=it['pos'];vx,vy=it['velocity'];big=it['kind'] in (2,4)
        if it.get('mode',0)!=0 or vy<=0 or abs(vx)>2:continue
        eta=(p[1]-y)/vy
        if not -2<=eta<=(50 if big else 35):continue
        tx=x+vx*max(0,eta);dx=tx-p[0]
        if abs(dx)>min(112 if big else 70,speed*max(0,eta)+8):continue
        sign=0 if abs(dx)<=6 else (1 if dx>0 else -1)
        if mode=='stream' and (not sign or sign!=route.get('direction') or abs(p[1]-route['target'][1])>48):continue
        if sign and not lo+12<=tx<=hi-12:continue
        opts.append((not big,abs(dx),it['slot'],sign,tx,it,eta))
    if not opts:return
    h=np.concatenate((np.asarray(s['bullets'],float).reshape(-1,5),enemy_hazards(np.asarray(s['enemies'],float).reshape(-1,6))))
    def gap(a,v,d,t):return swept(a[None,:],v[None,:],d,t,h,[],s['radius'],1)[0]
    ox,oy,focus=ACTIONS[previous];ov=np.array([ox,oy])*s['speeds'][(2 if ox and oy else 0)+int(focus)]
    zero=np.zeros(2);checked={}
    for _,dist,slot,sign,tx,it,eta in sorted(opts,key=lambda k:k[:3]):
        v=np.array([sign*speed,0]);end=p+8*v;delayed=p+2*ov
        if not lo<=end[0]<=hi or not lo<=delayed[0]+8*v[0]<=hi or not top<=delayed[1]<=bottom:continue
        if sign not in checked:checked[sign]=min(gap(p,v,8,0),gap(end,zero,37,8),gap(p,ov,2,0),gap(delayed,v,8,2),gap(delayed+8*v,zero,35,10))
        if checked[sign]<32:continue
        action=0 if not sign else 1 if sign<0 else 2
        return (action,np.array([p+v*2,p+v*5,end,end,end,end,end]),baseline[2]),dict(active=True,reason='wait_falling_p' if not sign else 'intercept_falling_p',slot=slot,kind=it['kind'],large=it['kind'] in (2,4),target=[tx,p[1]],clearance=float(checked[sign]))
