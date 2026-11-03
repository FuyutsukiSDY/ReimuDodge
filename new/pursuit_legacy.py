"""New-edition horizontal pursuit; never overrides special routes or lasers."""
import numpy as np
from engine import ACTIONS,swept
from enemies import enemy_hazards

class Pursuit:
    def __init__(self):self.reset()
    def reset(self):self.target=None;self.direction=0;self.turned=-10000;self.frame=-1
    def choose(self,s,previous,baseline,enabled):
        info={'active':False,'reason':'disabled'}
        def reject(reason):info['reason']=reason;return baseline,info
        if not enabled:self.reset();return baseline,info
        if s['frame']<self.frame:self.reset()
        self.frame=s['frame']
        if s['state']!=0 or s['bomb_active'] or s['lasers']:return reject('state_or_laser')
        if s.get('route'):return reject('special_route')
        if baseline[2]>=1000:return reject('baseline_danger')
        p=np.asarray(s['player'],float);bounds=s['bounds'];en=np.asarray(s['enemies'],float).reshape(-1,6)
        eligible=en[(en[:,1]<p[1]-100)&(en[:,0]>=bounds[0]+56)&(en[:,0]<=bounds[2]-56)]
        if not len(eligible):self.target=None;return reject('no_target')
        metric=abs(eligible[:,0]-p[0]) if self.target is None else np.linalg.norm(eligible[:,:2]-self.target,axis=1)
        enemy=eligible[np.argmin(metric)];self.target=enemy[:2].copy()
        dx=enemy[0]-p[0];info['target']=self.target.tolist()
        if abs(dx)<20:return reject('aligned')
        direction=1 if dx>0 else -1
        if self.direction and direction!=self.direction and s['frame']-self.turned<45:return reject('reversal_cooldown')
        action=2 if direction>0 else 1
        if ACTIONS[previous][0]*direction<0:return reject('previous_opposite')
        velocity=np.array([direction*s['speeds'][1],0.])
        end=p+velocity*6
        if not bounds[0]+48<=end[0]<=bounds[2]-48:return reject('edge')
        b=np.asarray(s['bullets'],float).reshape(-1,5)
        hazards=np.concatenate((b,enemy_hazards(en)))
        def clearance(start,v,d,t):
            return float(swept(np.array([start]),np.array([v]),d,t,hazards,[],s['radius'],1.)[0])
        # Conservative enclosing circles deliberately require generous space.
        stationary=clearance(p,np.zeros(2),45,0)
        if stationary<28:return reject('local_pressure')
        move=min(clearance(p,velocity,6,0),clearance(end,np.zeros(2),39,6))
        if move<28:return reject('path_pressure')
        base_min=1e4;start=p;elapsed=0
        for i,point in enumerate(baseline[1]):
            duration=2 if i==0 else 3 if i==1 else 6
            base_min=min(base_min,clearance(start,(point-start)/duration,duration,elapsed))
            start=point;elapsed+=duration
        if move+1e-6<min(base_min,48):return reject('baseline_safer')
        old=ACTIONS[previous];speed=s['speeds'][3 if old[2] else 2] if old[0] and old[1] else s['speeds'][1 if old[2] else 0]
        old_v=np.array(old[:2])*speed
        if min(clearance(p,old_v,2,0),clearance(p+old_v*2,velocity,6,2))<28:return reject('input_delay')
        if direction!=self.direction:self.turned=s['frame'];self.direction=direction
        info.update(active=True,reason='safe_horizontal',clearance=move,baseline_clearance=base_min)
        return (action,np.array([p+velocity*2,p+velocity*5,end,end,end,end,end]),baseline[2]),info

