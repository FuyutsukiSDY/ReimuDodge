"""Early horizontal interception, target continuity and anti-reversal guard.
Enemy contact dimensions are NOT treated as measured shot hitboxes.
"""
import numpy as np
from engine import ACTIONS,swept
from enemies import enemy_hazards
from pursuit_legacy import Pursuit as Legacy

class Pursuit:
    def __init__(self):self.legacy=Legacy();self.reset()
    def reset(self):
        self.target=None;self.velocity=None;self.frame=-1;self.direction=0;self.last_motion=-1000
        self.legacy.reset()
    def choose(self,s,previous,baseline,enabled):
        info={'active':False,'reason':'disabled','policy':'P1'}
        def reject(reason):info['reason']=reason;return baseline,info
        if not enabled:self.reset();return baseline,info
        frame=s['frame'];dt=frame-self.frame
        if dt<0 or dt>120:self.reset();dt=0
        self.frame=frame
        horizontal=ACTIONS[previous][0]
        if horizontal:self.direction=horizontal;self.last_motion=frame
        if s.get('route'):
            self.target=None
            return self.legacy.choose(s,previous,baseline,enabled)
        if s['state']!=0 or s['bomb_active'] or s['lasers']:return reject('state_or_laser')
        if baseline[2]>=1000:return reject('baseline_danger')
        p=np.asarray(s['player'],float);lo=np.asarray(s['bounds'][:2]);hi=np.asarray(s['bounds'][2:])
        en=np.asarray(s['enemies'],float).reshape(-1,6)
        eligible=en[(en[:,1]<p[1]-100)&(en[:,0]>=lo[0]+32)&(en[:,0]<=hi[0]-32)]
        if not len(eligible):self.target=None;return reject('no_target')
        # Match a short predicted track, not merely whichever enemy is nearest now.
        predicted=None if self.target is None else self.target+self.velocity*max(0,min(dt,12))
        if predicted is not None:
            distance=np.linalg.norm(eligible[:,:2]-predicted,axis=1);idx=int(np.argmin(distance))
            if distance[idx]>48:self.target=None
        if self.target is None:
            metric=abs(eligible[:,0]-p[0])+np.maximum(0,eligible[:,1]-180)*.15
            if self.direction and frame-self.last_motion<60:
                metric+=((eligible[:,0]-p[0])*self.direction<0)*80
            idx=int(np.argmin(metric))
        enemy=eligible[idx];self.target=enemy[:2].copy();self.velocity=np.clip(enemy[2:4],-4,4)
        # Small capped lead; no assumed projectile speed or unverified hitbox width.
        target_x=float(np.clip(enemy[0]+np.clip(enemy[2]*6,-16,16),lo[0]+32,hi[0]-32))
        dx=target_x-p[0];info.update(target=self.target.tolist(),aim_x=target_x)
        hazards=np.concatenate((np.asarray(s['bullets'],float).reshape(-1,5),enemy_hazards(en)))
        def gap(start,v,d,t):
            return float(swept(np.asarray([start]),np.asarray([v]),d,t,hazards,[],s['radius'],1)[0])
        old=ACTIONS[previous];speed=s['speeds'][3 if old[2] else 2] if old[0] and old[1] else s['speeds'][1 if old[2] else 0]
        oldv=np.asarray(old[:2])*speed
        stationary=gap(p,np.zeros(2),35,0)
        if stationary<28:return reject('local_pressure')
        base_gap=1e4;start=p;elapsed=0
        for i,point in enumerate(baseline[1]):
            duration=2 if i==0 else 3 if i==1 else 6
            base_gap=min(base_gap,gap(start,(point-start)/duration,duration,elapsed))
            start=point;elapsed+=duration
        aligned=abs(dx)<=12
        direction=0 if aligned else (1 if dx>0 else -1)
        if direction and self.direction and direction!=self.direction and frame-self.last_motion<60:
            return reject('aimed_volley_no_reversal')
        # Fast interception only across a roomy, fully checked horizontal lane.
        choices=[(0,np.zeros(2),28)] if aligned else [(2 if direction>0 else 1,np.array([direction*s['speeds'][1],0.]),28)]
        if not aligned and abs(dx)>64 and stationary>=40:
            choices.insert(0,(10 if direction>0 else 9,np.array([direction*s['speeds'][0],0.]),40))
        for action,v,reserve in choices:
            end=p+v*6
            if not lo[0]+24<=end[0]<=hi[0]-24:continue
            clear=min(gap(p,v,6,0),gap(end,np.zeros(2),29,6))
            delayed=p+oldv*2
            if np.any(delayed<lo) or np.any(delayed>hi):continue
            if np.any(delayed+v*6<lo) or np.any(delayed+v*6>hi):continue
            clear=min(clear,gap(p,oldv,2,0),gap(delayed,v,6,2),gap(delayed+v*6,np.zeros(2),27,8))
            if clear<max(reserve,min(base_gap,36)):continue
            info.update(active=True,reason='hold_firing_lane' if aligned else 'early_intercept',clearance=clear,baseline_clearance=base_gap,fast=not ACTIONS[action][2])
            return (action,np.array([p+v*2,p+v*5,end,end,end,end,end]),baseline[2]),info
        return reject('path_pressure')
