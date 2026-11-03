"""Complete up-then-across candidates, validated every frame.
The waypoints persist; the entire remaining path must still be clear.
"""
import time
from route_learning import learner
import numpy as np
from engine import ACTIONS,swept
from enemies import enemy_hazards
from pursuit_p8 import Pursuit as Previous

class Pursuit(Previous):
    def reset(self):
        super().reset();self.crossing=None;self.cross_last=-1;self.cross_cooldown=-1

    def choose(self,s,previous,baseline,enabled):
        frame=s['frame']
        if frame<self.cross_last or frame-self.cross_last>90:self.reset()
        self.cross_last=frame
        # Authored routes, including aimed-stream guidance, keep priority.
        if not enabled or s.get('route') or s['state']!=0 or s.get('bomb_active') or s['lasers'] or baseline[2]>=1000:
            self.crossing=None
            return super().choose(s,previous,baseline,enabled)
        p=np.asarray(s['player'],float);lo=np.asarray(s['bounds'][:2]);hi=np.asarray(s['bounds'][2:])
        enemies=np.asarray(s['enemies'],float).reshape(-1,6)
        bosses=[b for b in s.get('bosses',[]) if b.get('damageable') and b['pos'][1]<p[1]-80]
        # First experiment is boss-specific; ordinary enemy pursuit is unchanged.
        if not bosses:
            self.crossing=None
            return super().choose(s,previous,baseline,enabled)
        boss=min(bosses,key=lambda b:abs(b['pos'][0]-p[0]))
        key=(s.get('game',{}).get('stage'),boss['slot'],boss.get('first_observed_frame'))
        aim=float(np.clip(boss['pos'][0],lo[0]+32,hi[0]-32))
        pending=self.crossing
        if pending and (pending['key']!=key or frame-pending['born']>140 or abs(aim-pending['aim'])>64):
            self.crossing=None;pending=None;self.cross_cooldown=frame+20
        if pending:
            points=[np.asarray(q,float) for q in pending['points']]
            while points and np.linalg.norm(points[0]-p)<=max(6,s['speeds'][0]*3):points.pop(0)
            if not points:
                self.crossing=None;self.cross_cooldown=frame+20
                return super().choose(s,previous,baseline,enabled)
            candidates=[(pending['rise'],pending['focus'],points)]
        else:
            if frame<self.cross_cooldown or abs(aim-p[0])<28 or p[1]<220:
                return super().choose(s,previous,baseline,enabled)
            # No immediate alignment reward is required during the upward leg.
            floor=max(lo[1]+24,160,float(boss['pos'][1])+100)
            candidates=[]
            for rise in (32,56,80,104,128):
                y=p[1]-rise
                if y<floor:continue
                for focus in (False,True):
                    candidates.append((rise,focus,[np.array([p[0],y]),np.array([aim,y])]))
        if not candidates:return super().choose(s,previous,baseline,enabled)
        started=time.perf_counter()
        hazards=np.concatenate((np.asarray(s['bullets'],float).reshape(-1,5),enemy_hazards(enemies)))
        def velocity(a):
            x,y,f=ACTIONS[a];speed=s['speeds'][3 if f else 2] if x and y else s['speeds'][1 if f else 0]
            return np.array([x,y],float)*speed
        oldv=velocity(previous)
        def gap(at,v,d,t):return float(swept(at[None,:],v[None,:],max(.001,d),t,hazards,[],s['radius'],1)[0])
        def inside(q):return np.all(q>=lo+8) and np.all(q<=hi-8)
        if not pending:
            horizontal=np.array([np.sign(aim-p[0])*s['speeds'][1],0.])
            eta=abs(aim-p[0])/s['speeds'][1]
            if gap(p,horizontal,eta,0)>=24 and gap(np.array([aim,p[1]]),np.zeros(2),16,eta)>=24:
                return super().choose(s,previous,baseline,enabled)
        valid=[];rejected={}
        for rise,focus,points in candidates:
            if time.perf_counter()-started>.006:break
            at=p.copy();elapsed=0.;legs=[];minimum=1e4;bad=None
            speed=float(s['speeds'][1 if focus else 0])
            # Axis segments avoid cutting the corner between waypoints.
            for point in points:
                delta=point-at
                for axis in (1,0):
                    # Commands are held across game frames. Do not chase sub-step
                    # coordinate errors before starting the horizontal leg.
                    if abs(delta[axis])<=max(6,speed*3):continue
                    v=np.zeros(2);v[axis]=np.sign(delta[axis])*speed
                    duration=abs(delta[axis])/speed;end=at+v*duration
                    if not inside(at) or not inside(end):bad='bounds';break
                    for delay in (0,2):
                        offset=oldv*delay
                        if not inside(at+offset) or not inside(end+offset):bad='delay_bounds';break
                        minimum=min(minimum,gap(at+offset,v,duration,elapsed+delay))
                    if bad or minimum<14:bad=bad or 'path_clearance';break
                    legs.append((at.copy(),v.copy(),duration,elapsed));at=end;elapsed+=duration
                if bad:break
            if not bad and (not legs or elapsed>105):bad='horizon'
            if not bad:
                minimum=min(minimum,gap(p,oldv,2,0),gap(at,np.zeros(2),16,elapsed),gap(at+oldv*2,np.zeros(2),16,elapsed+2))
                for delay in (0,2):
                    start=p+oldv*delay
                    if not inside(start+legs[0][1]*3):bad='first_command_bounds';break
                    minimum=min(minimum,gap(start,legs[0][1],3,delay))
                if minimum<14:bad='arrival_clearance'
            if not bad:
                exits=sum(inside(at+velocity(a)*6) and gap(at,velocity(a),6,elapsed)>=10 for a in range(1,9))
                if exits<2:bad='no_exit'
            if bad:
                rejected[bad]=rejected.get(bad,0)+1;continue
            valid.append((elapsed+rise*.12-min(minimum,40)*.2-learner.bias(s,boss,rise,focus),rise,focus,points,legs,minimum,exits))
        if not valid:
            if pending:self.cross_cooldown=frame+20
            self.crossing=None
            result,info=super().choose(s,previous,baseline,enabled)
            return result,dict(info,crossing_rejections=rejected,crossing_cancelled=bool(pending))
        _,rise,focus,points,legs,minimum,exits=min(valid,key=lambda v:v[0])
        # Preserve fixed waypoints until reached, rather than shifting the goal
        # upward on every frame. A moving boss may invalidate, never drag, them.
        self.crossing=dict(key=key,born=pending['born'] if pending else frame,aim=pending['aim'] if pending else aim,
                           rise=rise,focus=focus,points=[q.tolist() for q in points])
        self.bypass=None
        v=legs[0][1];action=next(a for a in range(1,17) if np.allclose(velocity(a),v))
        def position(t):
            for start,vel,duration,begin in legs:
                if t<=begin+duration:return start+vel*max(0,t-begin)
            start,vel,duration,begin=legs[-1];return start+vel*duration
        path=np.asarray([position(t) for t in (2,5,11,17,23,29,35)])
        return (action,path,baseline[2]),dict(active=True,policy='P10',reason='continue_crossing' if pending else 'up_then_across',
            target=points[-1].tolist(),waypoints=[q.tolist() for q in points],clearance=minimum,exits=exits,
            rise=rise,fast=not focus,planned_frames=sum(l[2] for l in legs),ms=(time.perf_counter()-started)*1000)
