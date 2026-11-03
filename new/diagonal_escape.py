"""Stage-two diagonal-volley detours, with receding-horizon safety checks."""
import numpy as np
import engine
from engine import ACTIONS,swept
from enemies import enemy_hazards

class Detour:
    def __init__(self):self.reset()
    def reset(self):self.target=None;self.born=0;self.last=-1;self.phase=None;self.timer=-1
    def choose(self,s,previous,baseline):
        frame=s['frame'];p=np.asarray(s['player'],float)
        if frame<self.last or frame-self.last>60:self.reset()
        self.last=frame
        if s.get('game',{}).get('stage')!=2 or s['state']!=0 or s.get('route') or s['lasers'] or s.get('bomb_active'):
            self.reset();return None
        b=np.asarray(s['bullets'],float).reshape(-1,5)
        diagonal=(abs(b[:,2])>.5)&(abs(b[:,3])>.5)
        bosses=[x for x in s.get('bosses',[]) if x.get('damageable')]
        if len(b)<24 or np.mean(diagonal)<.35 or not bosses:self.reset();return None
        boss=min(bosses,key=lambda x:abs(x['pos'][0]-p[0]))
        phase=(boss.get('slot'),boss.get('phase_start_hp'),boss.get('limit_frames'))
        timer=boss.get('timer_frames',0)
        if phase!=self.phase or timer<self.timer:
            self.target=None
        self.phase=phase;self.timer=timer
        if self.target is None:
            if 100<p[0]<284:return None
            self.target=np.array([float(np.clip(boss['pos'][0],128,256)),max(200,p[1]-64,boss['pos'][1]+96)])
            self.born=frame
        if frame-self.born>140 or np.linalg.norm(p-self.target)<16:self.reset();return None
        saved=dict(engine.last_search)
        try:
            candidate=engine.plan(p,b,[],s['speeds'],s['radius']+13,previous,depth=11,width=20,
                enemies=s['enemies'],bounds=s['bounds'],route_override=dict(mode='detour',target=self.target.tolist(),weight=.22))
        finally:engine.last_search.clear();engine.last_search.update(saved)
        a,path,cost=candidate
        if cost>=1000 or a==0 or np.linalg.norm(path[-1]-self.target)>np.linalg.norm(p-self.target)-16:return None
        hazards=np.concatenate((b,enemy_hazards(s['enemies'])))
        def vel(i):
            x,y,f=ACTIONS[i];speed=s['speeds'][3 if f else 2] if x and y else s['speeds'][1 if f else 0]
            return np.array([x,y])*speed
        lo=np.asarray(s['bounds'][:2])+6;hi=np.asarray(s['bounds'][2:])-6
        def inside(q):return np.all(q>=lo)&np.all(q<=hi)
        def gap(q,v,d,t):return float(swept(q[None,:],v[None,:],d,t,hazards,[],s['radius'],1)[0])
        old=vel(previous);minimum=gap(p,old,2,0)
        for delay in (0,1,2):
            q=p+old*delay
            if not inside(q) or not inside(q+vel(a)*3):return None
            minimum=min(minimum,gap(q,vel(a),3,delay))
        q=p.copy();elapsed=0
        for i,end in enumerate(path):
            dt=2 if i==0 else 3 if i==1 else 6
            v=(end-q)/dt
            for delay in (0,2):
                if not inside(q+old*delay) or not inside(end+old*delay):return None
                minimum=min(minimum,gap(q+old*delay,v,dt,elapsed+delay))
            q=end;elapsed+=dt
        minimum=min(minimum,gap(q,np.zeros(2),12,elapsed))
        if minimum<12:return None
        exits=sum(inside(q+vel(i)*6) and gap(q,vel(i),6,elapsed)>=10 for i in range(1,9))
        if exits<2:return None
        return candidate,dict(active=True,policy='P13',reason='diagonal_edge_detour',target=self.target.tolist(),clearance=minimum,exits=exits,horizon=elapsed)
