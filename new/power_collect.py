from pickup_p6 import intercept as early_intercept
"""Read-only P items and conservative collection overlay for the 0.8.12 planner."""
import struct
import numpy as np
from engine import plan,swept,ACTIONS
from enemies import enemy_hazards
POWER_RVA=0x53cad8
ITEM_RVA=0xbfb2f8
COUNT=1024
STRIDE=0x160
MAX_POWER=128

def read_power_items(reader):
    diagnostics={'invalid_items':0,'offscreen_items':0}
    reader.item_diagnostics=diagnostics
    power=struct.unpack('<H',reader.read(POWER_RVA,2))[0]
    if not 0<=power<=MAX_POWER:raise ValueError('火力数据超出范围')
    raw=reader.read(ITEM_RVA,COUNT*STRIDE);items=[];reader.collection_items=[]
    for i in range(COUNT):
        o=i*STRIDE
        if raw[o]!=1 or raw[o+0xc] not in (0,1) or raw[o+0x34] not in (0,2,3,4):continue
        x,y=struct.unpack_from('<2f',raw,o+0x10);vx,vy=struct.unpack_from('<2f',raw,o+0x1c)
        if not np.isfinite([x,y,vx,vy]).all() or abs(vx)>10 or abs(vy)>10 or abs(x)>5000 or abs(y)>5000:
            diagnostics['invalid_items']+=1
            continue
        if not(-32<=x<=416 and -32<=y<=480):
            diagnostics['offscreen_items']+=1
            continue
        # Ignore initial rising/bouncing motion and already auto-attracted items.
        reader.collection_items.append(dict(slot=i,kind=raw[o+0x34],mode=raw[o+0xc],pos=[x,y],velocity=[vx,vy]))
        if vy>=0 and raw[o+0xc]==0:items.append(dict(slot=i,kind=raw[o+0x34],pos=[x,y],velocity=[vx,vy]))
    return power,items

from p_intercept import intercept
def _choose_power(s,previous,baseline,enabled=True):
    pick=intercept(s,previous,baseline,enabled)
    if pick:return pick
    """Always return the original planner result unless every collection gate passes."""
    if not enabled or s.get('power') is None or s['power']>=MAX_POWER or s.get('pickup_error') or s.get('route') or s['state']!=0 or s['lasers'] or s.get('bomb_active') or baseline[2]>=1000:
        return baseline,None
    p=np.asarray(s['player'],float);bounds=s['bounds'];bullets=np.asarray(s['bullets'],float).reshape(-1,5)
    hazards=np.concatenate((bullets,enemy_hazards(s['enemies'])))
    # Do not depart for items if a current hazard is predicted near the starting
    # area during the next second; never rely on invincibility or automatic Bomb.
    if swept(p[None,:],np.zeros((1,2)),60,0,hazards,[],s['radius'],0)[0]<64:return baseline,None
    candidates=[]
    for item in s.get('power_items',[]):
        q=np.asarray(item['pos']);distance=np.linalg.norm(q-p)
        big=item['kind'] in (2,4)  # Executable dispatch: +8 power / full power.
        if distance>(96 if big else 72) or q[1]<p[1]-(40 if big else 32) or q[1]<160:continue
        eta=min(24,distance/max(s['speeds'][1],.1))
        target=q+np.asarray(item['velocity'])*eta
        if not(bounds[0]+32<=target[0]<=bounds[2]-32 and 160<=target[1]<=bounds[3]-32):continue
        candidates.append((0 if big else 1,distance,item,target))
    if not candidates:return baseline,None
    # Prefer a safe large/full P. If its route fails, try the next candidate.
    for _,distance,item,target in sorted(candidates,key=lambda x:x[:2])[:3]:
        guide=dict(mode='power',target=target.tolist(),weight=.22)
        result=plan(p,bullets,[],s['speeds'],s['radius'],previous,enemies=s['enemies'],bounds=bounds,route_override=guide)
        action,path,cost=result
        if cost>=1000 or path is None:continue
        at=p.copy();elapsed=0;minimum=1e4
        for index,end in enumerate(path):
            duration=2 if index==0 else 3 if index==1 else 6
            v=(end-at)/duration
            minimum=min(minimum,float(swept(at[None,:],v[None,:],duration,elapsed,hazards,[],s['radius'],0)[0]))
            at=end;elapsed+=duration
        if minimum<24:continue
        if swept(at[None,:],np.zeros((1,2)),20,elapsed,hazards,[],s['radius'],0)[0]<32:continue
        # Preserve the collection clearance even when input is delayed two frames.
        x,y,focus=ACTIONS[previous]
        speed=s['speeds'][3 if focus else 2] if x and y else s['speeds'][1 if focus else 0]
        old_v=np.array([x,y])*speed
        first_v=(path[0]-p)/2
        delay=min(float(swept(p[None,:],old_v[None,:],2,0,hazards,[],s['radius'],0)[0]),
                  float(swept((p+old_v*2)[None,:],first_v[None,:],3,2,hazards,[],s['radius'],0)[0]))
        if delay<24:continue
        if np.linalg.norm(at-target)>=np.linalg.norm(p-target)-4:continue
        return result,dict(active=True,slot=item['slot'],kind=item['kind'],large=item['kind'] in (2,4),target=target.tolist(),clearance=minimum)
    return baseline,None


from autocollect_p8 import controller
from big_p_lane import choose as big_lane

def choose(s,previous,baseline,enabled=True):
    upper=controller.choose(s,previous,baseline,enabled)
    if upper is not None and upper[1].get("active"):return upper
    lane=big_lane(s,previous,baseline,enabled)
    if lane is not None:return lane
    # This proxy only describes collectible needs to the planner. It never
    # writes resource counters or changes the snapshot used by auto Bomb.
    eligible=[it for it in s.get('power_items',[]) if
              (it['kind']==3 and 0<=s.get('bombs',-1)<7) or
              (it['kind'] in (0,2,4) and s.get('power') is not None and s['power']<128)]
    proxy=dict(s,power_items=eligible)
    if any(it['kind']==3 for it in eligible) and proxy.get('power')==128:proxy['power']=127
    result=early_intercept(proxy,previous,baseline,enabled)
    s['pickup_search']=proxy.get('pickup_search')
    if result:
        action,info=result
        info=dict(info,resource='bomb' if info['kind']==3 else 'power')
        return action,info
    # Legacy pickup interprets only P kinds; never pass B to that fallback.
    proxy['power_items']=[it for it in eligible if it['kind'] in (0,2,4)]
    proxy['power']=s.get('power')
    return _choose_power(proxy,previous,baseline,enabled)
