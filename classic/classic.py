"""Steam Classic decoder, locked by editions.py to the inspected executable.

Rectangle collision callers: E490 (bullets), 20DFD (enemy contact), E847
(laser). Circles remain as broad-phase data; half sizes refine the planner.
No process writes here. Classic does not inherit New Classic card signatures.
"""
import struct
import numpy as np

POOL_RVA=0xa7e1e8
STRIDE=0xfd0
COUNT=256

def guidance(s):
    """Reserve retreat room in Classic stage 3-6 dense single-enemy volleys.

    Enable soft edge/bottom costs, not a fixed destination or forbidden zone.
    The collision planner can ignore these costs to escape an immediate hazard.
    """
    if s.get('stage') in (1,3,4) and not s['lasers'] and len(s['enemies']):
        enemies=np.asarray(s['enemies'],float).reshape(-1,6)
        above=enemies[enemies[:,1]<s['player'][1]-40]
        if len(above):
            # No pursuit: output alignment must not pull us back into aimed fire.
            early=s.get('stage')==1
            return dict(mode='classic_boss',target=list(s['player']),weight=0.,
                        retreat=64 if early else 80,edge=56 if early else 72,
                        strength=.012 if early else .02,lookahead=len(s['bullets'])>=48,
                        reversal_cost=2.)
    if s.get('stage') not in (3,4,5,6) or s['lasers'] or not 1<=len(s['enemies'])<=2 or len(s['bullets'])<(48 if s.get('stage') in (3,4) else 16):
        return None
    return dict(mode='classic_boss',target=list(s['player']),weight=0.,retreat=96,edge=88,strength=.02,lookahead=True)

def stream_retreat(route,stage):
    if route and route['mode']=='stream' and stage==3:
        # Do not let a sustained lateral target drag the player into a corner.
        target=[float(np.clip(route['target'][0],104,280)),min(route['target'][1],320)]
        return dict(route,target=target,weight=.06,classic_retreat=True,retreat=112,edge=104,strength=.035)
    if route and route['mode']=='stream' and stage in (3,4,5,6):
        return dict(route,classic_retreat=True,retreat=96,edge=88,strength=.02)
    return route

def decode_enemies(raw):
    flags=np.ndarray((COUNT,3),'u1',raw,0xb4,(STRIDE,1))
    active=((flags[:,0]&128)!=0)&((flags[:,1]&7)==7)&((flags[:,2]&8)==0)
    slots=np.flatnonzero(active)
    pos=np.ndarray((COUNT,2),'<f4',raw,0xa8,(STRIDE,4))[active].astype(float)
    dims=np.ndarray((COUNT,2),'<f4',raw,0x2a4,(STRIDE,4))[active].astype(float)
    vel=np.ndarray((COUNT,2),'<f4',raw,0xfa4,(STRIDE,4))[active].astype(float)
    vel[(flags[active,0]&64)!=0,0]*=-1
    if not (np.isfinite(pos).all() and np.isfinite(dims).all() and np.isfinite(vel).all()
            and (abs(pos)<10000).all() and (abs(vel)<1000).all()
            and (dims>=0).all() and (dims<2048).all()):
        raise RuntimeError('原典敌机本体数据异常')
    return slots,np.column_stack((pos,vel,dims*float(np.float32(2/3))*.5))

def laser_window(phase,counter,warmup,duration,fade,early,late):
    values=(counter,warmup,duration,fade,early,late)
    if any(v<0 or v>10000000 for v in values):return {}
    tail=min(fade,late)
    if phase==0:return dict(danger_from=max(0,early-counter-1),danger_until=max(0,warmup-counter)+duration+tail+3)
    if phase==1:return dict(danger_from=0,danger_until=max(0,duration-counter)+tail+3)
    return dict(danger_from=0,danger_until=max(0,tail-counter)+2)

def snapshot(reader):
    from reader import SnapshotNotReady
    raw=reader.read(0x955410,0xe8818+64*0x278)
    frame=struct.unpack_from('<I',raw,4)[0]
    pool=memoryview(raw)[8:8+640*0x5d0]
    states=np.ndarray((640,),'<u2',pool,0x44,(0x5d0,))
    pos=np.ndarray((640,2),'<f4',pool,0x30,(0x5d0,4))
    vel=np.ndarray((640,2),'<f4',pool,8,(0x5d0,4))
    dims=np.ndarray((640,2),'<f4',pool,0x5a4,(0x5d0,4))
    active=(states>=1)&(states<=4)
    valid=np.isfinite(pos).all(1)&np.isfinite(vel).all(1)&np.isfinite(dims).all(1)
    valid&=(abs(pos)<5000).all(1)&(abs(vel)<100).all(1)&(dims>0).all(1)&(dims<512).all(1)
    if np.any(active&~valid):
        raise SnapshotNotReady(dict(edition='classic',frame=frame,count=int(np.sum(active&~valid)),slots=np.flatnonzero(active&~valid)[:8].tolist()))
    bullets=np.column_stack((pos[active],vel[active],np.linalg.norm(dims[active].astype(float)*.5,axis=1)))
    lasers=[]
    for slot in range(64):
        o=0xe8818+slot*0x278
        phase=raw[o+0x270]
        if not raw[o+0x254] or phase not in (0,1,2):continue
        width=struct.unpack_from('<f',raw,o+4)[0]
        start,end=struct.unpack_from('<2f',raw,o+0x10)
        angle=struct.unpack_from('<f',raw,o+0x240)[0]
        origin=struct.unpack_from('<2f',raw,o+0x258)
        speed=struct.unpack_from('<f',raw,o+0x24c)[0]
        if not np.isfinite([width,start,end,angle,*origin,speed]).all():raise RuntimeError('原典激光数据异常')
        if width<=0 or end<=start:continue
        counter=struct.unpack_from('<i',raw,o+0xc)[0]
        duration,warmup=struct.unpack_from('<i',raw,o+0x248)[0],struct.unpack_from('<i',raw,o+0x250)[0]
        fade=struct.unpack_from('<i',raw,o+0x18)[0]
        early,late=struct.unpack_from('<i',raw,o+0x26c)[0],struct.unpack_from('<i',raw,o)[0]
        window=laser_window(phase,counter,warmup,duration,fade,early,late)
        # E5DC passes stored width * .5 as the full collision rectangle width;
        # 4C96C halves that again to test its edges. Keep render width separately.
        lasers.append(dict(slot=slot,origin=origin,start=start,end=end,width=width*.5,render_width=width,angle=angle,speed=speed,
            firing=phase==1 or (phase==0 and counter>=early) or (phase==2 and counter<min(late,fade)),
            phase=phase,phase_counter=counter,warmup=warmup,duration=duration,**window))
    player=reader.read(0xbbfc18,0x194)
    p=struct.unpack_from('<2f',player,0x20)
    scale=struct.unpack_from('<2f',player,0)
    half=struct.unpack_from('<2f',player,0x3c)
    radius=float(np.linalg.norm(half))
    speeds=struct.unpack_from('<4f',player,0x158)
    if not np.isfinite([*p,*half,*speeds]).all() or not (0<radius<20) or not all(0<s<20 for s in speeds):raise RuntimeError('原典自机数据异常')
    if not all(.9<s<1.1 for s in scale):raise RuntimeError('原典自机处于特殊移动状态，请稍后启动')
    bx,by,bw,bh=struct.unpack('<4f',reader.read(0x3ee7f4,16))
    if not np.isfinite([bx,by,bw,bh]).all() or not (0<=bx<384 and 0<=by<448 and 0<bw<=384 and 0<bh<=448):raise RuntimeError('原典边界异常')
    return dict(edition='classic',stage=struct.unpack('<i',reader.read(0x3ed030,4))[0],frame=frame,player=p,speeds=speeds,radius=radius,bullets=bullets,
        bullet_half=dims[active].astype(float)*.5,player_half=half,
        lasers=reader.laser_tracker.update(lasers,frame),enemies=reader.enemy_tracker.update(reader.read(POOL_RVA,COUNT*STRIDE),frame),
        bounds=(bx,by,bx+bw,by+bh),state=player[0x190],invincible=reader.invincible(),
        bombs=struct.unpack('<b',reader.read(0x3ee805,1))[0],bomb_active=bool(reader.read(0xbc21c0,1)[0]),
        death_window=struct.unpack_from('<i',player,0x2c)[0])
