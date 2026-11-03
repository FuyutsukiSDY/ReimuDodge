"""Soft tactical preferences inferred from current hazard geometry.
No timers or prerecorded key sequences. Collision checks always rank first.
"""
import numpy as np


class LateralStream:
    """Keep a direction across dodges during multi-enemy volleys.

    This is a soft multi-enemy tactic, not proof that a bullet is aimed.
    Never carry it into lasers, boss patterns, a new scene or a respawn.
    """
    def __init__(self):self.reset()

    def reset(self):
        self.direction=0;self.frame=None;self.anchor_y=None

    def update(self,frame,player,bullets,lasers,enemies,bounds,existing=None,state=0):
        if self.frame is not None and (frame<self.frame or frame-self.frame>120):self.reset()
        self.frame=frame
        if existing or lasers or state!=0 or len(enemies)<2:
            self.reset()
            return existing
        p=np.asarray(player,float)
        b=np.asarray(bullets,float).reshape(-1,5)
        if not self.direction:
            # Start before a dense volley reaches the player, while there is
            # still horizontal space. Retain the tactic if enemy count dips to 2.
            if len(enemies)<3 or len(b)<12:return None
            self.direction=1 if p[0]<(bounds[0]+bounds[2])*.5 else -1
            self.anchor_y=float(np.clip(p[1],bounds[3]-92,bounds[3]-60))
        left,right=bounds[0]+56,bounds[2]-56
        if self.direction>0 and p[0]>=right:self.direction=-1
        elif self.direction<0 and p[0]<=left:self.direction=1
        return dict(mode='stream',target=[right if self.direction>0 else left,self.anchor_y],
                    weight=.14,direction=self.direction)


def chase_detour(player,target,bullets,bounds):
    """Prefer a clear short corridor when the usual orbit points into a trail.
    This only supplies a waypoint; the planner still checks the actual path.
    """
    delta=target-player
    heading=np.arctan2(delta[1],delta[0])
    offsets=np.radians([0,30,-30,60,-60,90,-90])
    directions=np.column_stack((np.cos(heading+offsets),np.sin(heading+offsets)))
    velocity=directions*2
    relative=player-bullets[:,:2]
    rv=velocity[:,None,:]-bullets[None,:,2:4]
    t=np.clip(-np.sum(relative[None,:,:]*rv,axis=2)/np.maximum(np.sum(rv*rv,axis=2),1e-9),0,45)
    clearance=(np.linalg.norm(relative[None,:,:]+rv*t[:,:,None],axis=2)-bullets[None,:,4]-2).min(axis=1)
    ends=player+velocity*45
    center=np.array([(bounds[0]+bounds[2])*.5,(bounds[1]+bounds[3])*.5])
    radial=player-center
    tangent=np.array([-radial[1],radial[0]])/max(np.linalg.norm(radial),1)
    # A clear reverse corridor may be the wake we just laid down. Keep
    # strategic waypoints advancing around the orbit, with wall clearance.
    progress=directions@tangent
    valid=(ends[:,0]>=bounds[0]+24)&(ends[:,0]<=bounds[2]-24)&(ends[:,1]>=bounds[1]+64)&(ends[:,1]<=bounds[3]-24)&(progress>.2)
    if clearance[0]>=6 and valid[0]:return target,False
    scores=np.minimum(clearance,24)+np.cos(offsets)*6
    scores=np.where(valid & (clearance>=6) & (clearance>=clearance[0]+8),scores,-np.inf)
    best=int(np.argmax(scores))
    if not np.isfinite(scores[best]):return target,False
    return ends[best],True


def guidance(player,bullets,lasers,enemies,bounds=(8,16,376,432)):
    p=np.asarray(player,float)
    # Long rotating blade with its short-lived thin trailing rays. Restrict the
    # signature to this shape; normal straight lasers keep the baseline policy.
    blades=[l for l in lasers if 380<=l['end']<=440 and 28<=l['start']<=36 and 20<=l['width']<=28 and abs(l['speed'])<.01]
    if blades:
        translating=[l for l in blades if 395<=l['end']<=405 and abs(np.cos(l['angle']))<.02 and np.sin(l['angle'])>.99]
        if translating:
            blade=translating[0]
            vx=blade.get('origin_velocity',[0,0])[0]
            direction=np.sign(vx) if abs(vx)>.1 else (1 if blade['origin'][0]<192 else -1)
            # A lateral sweep starts faster than the player. Use its warning
            # to get ahead, instead of following a moving pivot after firing.
            target=[bounds[2]-36 if direction>0 else bounds[0]+36,150.]
            return dict(mode='sweep',phase='translate',target=target,weight=.35)
        origin=np.mean([l['origin'] for l in blades],axis=0)
        return dict(mode='sweep',target=(origin+[0,95]).tolist(),weight=.10)
    crosses=[l for l in lasers if 200<=l['end']<=230 and abs(l['start'])<.01 and 20<=l['width']<=28 and abs(l['speed'])<.01]
    if len(crosses)>=6:
        # Recenter during the warning only. Once any beam fires, release the
        # horizontal target so it cannot pull the player back across a beam.
        if all(not l.get('firing',False) and l.get('danger_from',0)>5 for l in crosses):
            return dict(mode='cross',phase='prepare',target=[(bounds[0]+bounds[2])*.5,bounds[3]-12],weight=.35)
        return dict(mode='cross',target=[float(p[0]),bounds[3]-12],weight=.25)
    b=np.asarray(bullets,float).reshape(-1,5)
    if len(b)>=12 and not lasers and not len(enemies):
        trail=(abs(b[:,4]-3)<.01)&(abs(np.linalg.norm(b[:,2:4],axis=1)-.5)<.02)
        if np.mean(trail)>.95:
            center=np.array([(bounds[0]+bounds[2])*.5,(bounds[1]+bounds[3])*.5])
            axes=np.array([(bounds[2]-bounds[0])*.5-30,(bounds[3]-bounds[1])*.5-30])
            relative=(p-center)/axes
            angle=np.arctan2(relative[1],relative[0])+.65
            target=center+axes*np.array([np.cos(angle),np.sin(angle)])
            # Turn across the upper field before the orbit reaches the ceiling.
            # Keep vertical room for dodges instead of guiding toward y=46.
            target[1]=max(target[1],bounds[1]+80)
            target,detour=chase_detour(p,target,b,bounds)
            return dict(mode='chase',target=target.tolist(),weight=.14,detour=detour)
    return None

