"""Classic-only read-only item decoder and short, safety-gated pickup moves."""
import struct
import numpy as np
from engine import ACTIONS,swept
from enemies import enemy_hazards
POWER_RVA=0x3ed034
ITEM_RVA=0xb7d268
STRIDE=0x150
COUNT=512
MAX_POWER=128

def read_power_items(reader):
    if reader.edition!='classic':raise ValueError('仅支持原典道具')
    power=struct.unpack('<H',reader.read(POWER_RVA,2))[0]
    if not 0<=power<=128:raise ValueError('火力数据异常')
    if power==128:return power,[]
    raw=reader.read(ITEM_RVA,COUNT*STRIDE);items=[]
    for slot in range(COUNT):
        o=slot*STRIDE;kind=raw[o+0x34];mode=raw[o+12]
        if raw[o]!=1 or kind not in (0,2,4) or mode not in (0,2):continue
        x,y=struct.unpack_from('<2f',raw,o+16);vx,vy=struct.unpack_from('<2f',raw,o+28)
        if not np.isfinite([x,y,vx,vy]).all() or not(-32<=x<=416 and -64<=y<=480 and abs(vx)<=12 and abs(vy)<=12):raise ValueError('道具坐标异常')
        items.append(dict(slot=slot,kind=kind,mode=mode,pos=[x,y],velocity=[vx,vy]))
    return power,items

def choose(s,previous,baseline,enabled=True):
    info={'active':False,'reason':'disabled'}
    def reject(reason):info['reason']=reason;return baseline,info
    if not enabled:return baseline,info
    if s.get('power') is None or s.get('pickup_error'):return reject('unknown_power')
    if s['power']>=128:return reject('max_power')
    if s['state']!=0 or s['bomb_active'] or s['lasers'] or baseline[2]>=1000:return reject('danger_state')
    if s.get('route') and s['route']['mode']!='classic_boss':return reject('special_route')
    p=np.asarray(s['player'],float);bounds=s['bounds']
    b=np.asarray(s['bullets'],float).reshape(-1,5);en=np.asarray(s['enemies'],float).reshape(-1,6)
    hazards=np.concatenate((b,enemy_hazards(en)))
    def gap(at,v,d,t):return float(swept(np.array([at]),np.array([v]),d,t,hazards,[],s['radius'],1)[0])
    if gap(p,np.zeros(2),45,0)<32:return reject('local_pressure')
    candidates=[]
    for item in s.get('power_items',[]):
        big=item['kind'] in (2,4);q=np.array(item['pos']);iv=np.array(item['velocity']);distance=np.linalg.norm(q-p)
        # Spawn animation accelerates; wait for steady falling mode before pursuit.
        if item['mode']!=0 or iv[1]<0:continue
        if distance>(144 if big else 80) or q[1]<p[1]-(56 if big else 24) or q[1]<200:continue
        target=q+iv*min(24,distance/max(s['speeds'][1],.1))
        if not(bounds[0]+24<=target[0]<=bounds[2]-24 and 200<=target[1]<=bounds[3]-8):continue
        for action in range(1,9):
            x,y,f=ACTIONS[action];speed=s['speeds'][3 if x and y else 1];v=np.array([x,y])*speed;end=p+v*8
            if not(bounds[0]+24<=end[0]<=bounds[2]-24 and 200<=end[1]<=bounds[3]-12):continue
            gain=np.linalg.norm(p-target)-np.linalg.norm(end-target)
            if gain<3:continue
            clear=min(gap(p,v,8,0),gap(end,np.zeros(2),37,8))
            if clear<24:continue
            ox,oy,focus=ACTIONS[previous];os=s['speeds'][3 if focus else 2] if ox and oy else s['speeds'][1 if focus else 0];ov=np.array([ox,oy])*os
            if min(gap(p,ov,2,0),gap(p+ov*2,v,8,2))<24:continue
            if ox*x<0 and clear<48:continue
            candidates.append((0 if big else 1,distance-gain*2,action,v,clear,item,target))
    if not candidates:return reject('no_safe_item')
    _,_,action,v,clear,item,target=min(candidates,key=lambda c:c[:2])
    end=p+v*8;path=np.array([p+v*2,p+v*5,end,end,end,end,end])
    info.update(active=True,reason='safe_large_p' if item['kind'] in (2,4) else 'safe_small_p',slot=item['slot'],kind=item['kind'],target=target.tolist(),clearance=clear)
    return (action,path,baseline[2]),info
