"""Short checked bypasses when horizontal pursuit cannot find a safe lane."""
import time
import numpy as np
import engine
from engine import ACTIONS,swept
from enemies import enemy_hazards
from pursuit_p1 import Pursuit as Horizontal

class Pursuit(Horizontal):
    def reset(self):
        super().reset()
        self.bypass=None
    def choose(self,s,previous,baseline,enabled):
        result,info=super().choose(s,previous,baseline,enabled)
        if not enabled or s.get('route') or s['lasers'] or s['state']!=0 or s.get('bomb_active'):
            self.bypass=None
            return result,info
        if self.target is None:
            self.bypass=None
            return result,info
        p=np.array(s['player'],float);xmin,top,xmax,bottom=s['bounds'];frame=s['frame']
        target_x=float(info.get('aim_x',self.target[0]))
        pending=self.bypass
        if pending is not None:
            # Bounded episode, stable enemy and fixed vertical waypoint. Never
            # continually move the waypoint upward as the player approaches it.
            if (frame-pending['born']>90 or frame<pending['last'] or
                np.linalg.norm(self.target-pending['enemy'])>64 or
                frame-pending['last']>24):
                self.bypass=None;pending=None
        continuing=pending is not None
        if continuing:
            target=pending['target'].copy()
            dt=max(0,min(frame-pending['last'],12))
            target[0]+=np.clip(target_x-target[0],-2*dt,2*dt)
            if np.linalg.norm(p-target)<=12:
                self.bypass=None
                info=dict(info,bypass_completed=True)
                return result,info
            floor=pending['floor']
        else:
            if info.get('active') or info.get('reason') not in ('local_pressure','path_pressure'):return result,info
            if p[1]<260 or abs(target_x-p[0])<24:return result,info
            target=np.array([target_x,max(240,p[1]-64,self.target[1]+120)])
            if target[1]>p[1]-12:return result,info
            floor=max(top,240,p[1]-72)
        if self.direction and (target[0]-p[0])*self.direction<-12 and frame-self.last_motion<60:
            self.bypass=None
            return result,dict(info,bypass_cancelled='enemy_changed_side')
        started=time.perf_counter();detail=dict(active=False,reason='bypass_rejected',policy='P5',previous_reason=info['reason'],target=target.tolist(),continuing=continuing)
        hazards=np.concatenate((np.asarray(s['bullets'],float).reshape(-1,5),enemy_hazards(s['enemies'])))
        def vel(a):
            x,y,f=ACTIONS[a];speed=s['speeds'][3 if f else 2] if x and y else s['speeds'][1 if f else 0]
            return np.array([x,y])*speed
        def gap(at,v,d,t):return float(swept(at[None,:],v[None,:],d,t,hazards,[],s['radius'],1)[0])
        def inside(at):return xmin<=at[0]<=xmax and floor<=at[1]<=bottom
        saved=dict(engine.last_search)
        try:
            candidate=engine.plan(p,s['bullets'],[],s['speeds'],s['radius']+23,previous,
                depth=7,width=10,enemies=s['enemies'],bounds=s['bounds'],
                route_override=dict(mode='chase',target=target.tolist(),weight=.18))
        finally:
            engine.last_search.clear();engine.last_search.update(saved)
        a,path,cost=candidate
        def reject(why):
            self.bypass=None
            detail.update(reason=why,ms=(time.perf_counter()-started)*1000)
            return result,detail
        if time.perf_counter()-started>.008:return reject('bypass_budget')
        if cost>=1000 or a==0:return reject('bypass_no_safe_plan')
        if ACTIONS[a][0]*self.direction<0 and s['frame']-self.last_motion<60:return reject('bypass_reversal')
        if np.linalg.norm(path[-1]-target)>np.linalg.norm(p-target)-min(12,max(0,np.linalg.norm(p-target)-8)):return reject('bypass_no_progress')
        if not continuing and abs(path[-1,0]-target_x)>abs(p[0]-target_x)-8:return reject('bypass_no_alignment_gain')
        oldv=vel(previous);minimum=gap(p,oldv,2,0)
        # Protect the actual first command even across a short input delay.
        for delay in (0,1,2):
            start=p+oldv*delay;end=start+vel(a)*3
            if not inside(start) or not inside(end):return reject('bypass_bounds')
            minimum=min(minimum,gap(start,vel(a),3,delay))
        at=p;elapsed=0
        for i,end in enumerate(path):
            duration=2 if i==0 else 3 if i==1 else 6
            v=(end-at)/duration
            for delay in (0,2):
                offset=oldv*delay
                if not inside(at+offset) or not inside(end+offset):return reject('bypass_bounds')
                minimum=min(minimum,gap(at+offset,v,duration,elapsed+delay))
            at=end;elapsed+=duration
        minimum=min(minimum,gap(at,np.zeros(2),18,elapsed),gap(at+oldv*2,np.zeros(2),18,elapsed+2))
        if minimum<24:return reject('bypass_clearance')
        # A safe stop alone is insufficient: retain at least two escape directions.
        exits=0
        for next_a in range(1,9):
            v=vel(next_a)
            if inside(at+v*6) and gap(at,v,6,elapsed)>=12:exits+=1
        if exits<2:return reject('bypass_no_exit')
        self.bypass=dict(target=target.copy(),enemy=self.target.copy(),floor=floor,born=pending['born'] if continuing else frame,last=frame)
        detail.update(active=True,reason='continue_safe_bypass' if continuing else 'safe_short_bypass',clearance=minimum,exits=exits,ms=(time.perf_counter()-started)*1000)
        return candidate,detail
