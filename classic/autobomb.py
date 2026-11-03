"""Predict imminent contact; never use distant planner cost alone to bomb."""
import numpy as np
from engine import ACTIONS, laser_clearance
from enemies import enemy_hazards

def velocity(action,speeds):
    x,y,focus=ACTIONS[action]
    speed=speeds[3 if focus else 2] if x and y else speeds[1 if focus else 0]
    return np.array([x*speed,y*speed],float)

def imminent(s,action,previous=0):
    p=np.array(s['player'],float);v=velocity(action,s['speeds'])
    old=velocity(previous,s['speeds'])
    b=np.asarray(s['bullets'],float).reshape(-1,5)
    enemies=enemy_hazards(s.get('enemies',()))
    # Two-frame input latency followed by three frames of the chosen movement.
    for origin,motion,start,duration in [(p,old,0,2),(p+old*2,v,2,3)]:
        for hazards,label in ((b,'即将接触敌弹'),(enemies,'即将撞上敌机本体')):
            if not len(hazards):continue
            relative=origin-(hazards[:,:2]+hazards[:,2:4]*start)
            rv=motion-hazards[:,2:4]
            t=np.clip(-np.sum(relative*rv,axis=1)/np.maximum(np.sum(rv*rv,axis=1),1e-9),0,duration)
            distance=np.linalg.norm(relative+rv*t[:,None],axis=1)
            if np.any(distance<=hazards[:,4]+s['radius']+.6):return label
        lasers=[l for l in s['lasers'] if l.get('firing',False) or 'danger_from' in l]
        if lasers:
            dt=np.arange(0,duration+.01,.5)
            points=origin+motion*dt[:,None]
            # laser_clearance includes a 2px planner margin; Bomb keeps .6px.
            if np.any(laser_clearance(points,lasers,start+dt,s['radius'])+1.4<=0):
                return '即将接触激光'
    return None

class BombGuard:
    def __init__(self):
        self.last_frame=-10000;self.pulse_until=-1;self.wall_until=0;self.emergency_used=False
    def reason(self,s,action,previous,enabled,preview,deathbomb_only=False):
        if s['state']!=2:self.emergency_used=False
        if not enabled or preview or s['invincible'] or s['bomb_active'] or not 0<s['bombs']<=99:return None
        if s['frame']<self.last_frame:self.last_frame=-10000
        if s['state']==2:
            # A predictive press may not have been accepted. Permit one new
            # edge inside the death window, after a full released game frame.
            if s['death_window']>0 and not self.emergency_used and s['frame']-self.last_frame>=3:
                return '刚中弹，尝试决死 Bomb'
            return None
        if deathbomb_only:return None
        if s['frame']-self.last_frame<45:return None
        if s['state']!=0:return None
        return imminent(s,action,previous)
    def mark(self,frame,now,emergency=False):
        self.last_frame=frame;self.pulse_until=frame+2;self.wall_until=now+.08
        if emergency:self.emergency_used=True
    def holding(self,frame,now):
        return frame<self.pulse_until and now<self.wall_until
    def release(self):
        self.pulse_until=-1;self.wall_until=0
