"""Bounded stage policy trials. Authored routes and Bosses never participate."""
import numpy as np
import engine
from enemies import enemy_hazards
from route_learning import Learner

class StageLearner(Learner):
    def eligible(self,s):
        return (self.enabled and 1<=s.get('game',{}).get('stage',0)<=6
                and not s.get('bosses') and not s.get('route') and not s.get('lasers')
                and s['state']==0 and not s.get('invincible') and not s.get('bomb_active'))

    def context(self,s):
        g=s.get('game',{});b=np.asarray(s['bullets'],float).reshape(-1,5)
        diagonal=int(len(b)>0 and np.mean((abs(b[:,2])>.5)&(abs(b[:,3])>.5))>.4)
        return '|'.join(map(str,(g.get('stage'),g.get('difficulty'),g.get('character'),g.get('shot'),
            s['frame']//300,s.get('power',0)//16,int(s['player'][0]//96),min(3,len(b)//40),diagonal)))

    def quality(self,s,result,previous):
        a,path,cost=result
        if path is None or cost>=1000:return None
        hazards=np.concatenate((np.asarray(s['bullets'],float).reshape(-1,5),enemy_hazards(s['enemies'])))
        p=np.asarray(s['player'],float);lo=np.asarray(s['bounds'][:2])+4;hi=np.asarray(s['bounds'][2:])-4
        def velocity(i):
            x,y,f=engine.ACTIONS[i];v=s['speeds'][3 if f else 2] if x and y else s['speeds'][1 if f else 0]
            return np.array([x,y])*v
        def gap(q,v,dt,t):return float(engine.swept(q[None,:],v[None,:],dt,t,hazards,[],s['radius'],1)[0])
        old=velocity(previous);minimum=gap(p,old,2,0)
        for delay in (0,1,2):
            q=p+old*delay;t=delay
            for i,end in enumerate(path):
                end=np.asarray(end)+old*delay;dt=2 if i==0 else 3 if i==1 else 6
                if np.any(end<lo) or np.any(end>hi) or np.any(q<lo) or np.any(q>hi):return None
                minimum=min(minimum,gap(q,(end-q)/dt,dt,t));q=end;t+=dt
            minimum=min(minimum,gap(q,np.zeros(2),6,t))
        if minimum<8:return None
        q=np.asarray(path[-1]);t=5+max(0,len(path)-2)*6
        exits=sum(np.all(q+velocity(i)*6>=lo) and np.all(q+velocity(i)*6<=hi)
                  and gap(q,velocity(i),6,t)>=8 for i in range(1,9))
        return (minimum,exits) if exits>=2 else None

    def choose(self,s,previous,baseline):
        if not self.eligible(s) or s.get('pickup') or (s.get('pursuit') or {}).get('active'):
            return baseline,None
        if len(s['bullets'])<8:return baseline,None
        quality=self.quality(s,baseline,previous)
        if quality is None:return baseline,None
        context=self.context(s);variant=self.pending['variant'] if self.pending else None
        if variant is None:
            values=[self.data.get(context+'|'+v,dict(n=0,mean=0)) for v in ('base','center')]
            # Collect two safe trials per variant, then prefer bounded empirical score.
            variant=('base','center')[min(range(2),key=lambda i:values[i]['n'])] if min(v['n'] for v in values)<2 else ('base','center')[max(range(2),key=lambda i:max(-8,min(8,values[i]['mean'])))]
        result=baseline
        if variant=='center':
            saved=dict(engine.last_search)
            try:
                result=engine.plan(s['player'],s['bullets'],[],s['speeds'],s['radius'],previous,
                    enemies=s['enemies'],bounds=s['bounds'],depth=7,width=12,
                    route_override=dict(mode='stage_learning',target=[192,float(np.clip(s['player'][1],280,380))],weight=.035))
            finally:engine.last_search.clear();engine.last_search.update(saved)
            candidate_quality=self.quality(s,result,previous)
            # History cannot purchase a lower safety margin or fewer exits.
            if candidate_quality is None or candidate_quality[0]<min(quality[0],16) or candidate_quality[1]<quality[1]:return baseline,None
            quality=candidate_quality
        return result,dict(variant=variant,key=context+'|'+variant,clearance=quality[0],exits=quality[1])

    def commit(self,s,info,sent):
        if not sent or info is None or not self.eligible(s):self.cancel();return
        if self.pending:return
        self.pending=dict(key=info['key'],variant=info['variant'],frame=s['frame'],last=s['frame'],
            stage=s['game']['stage'],bombs=s['bombs'],damage=0,clearance=info['clearance'],exits=info['exits'])

    def observe(self,s):
        p=self.pending
        if not p:return
        dt=s['frame']-p['last']
        if (not self.enabled or dt<0 or dt>12 or s['game']['stage']!=p['stage']
                or s.get('invincible') or s.get('bomb_active') or s['bombs']!=p['bombs']):self.cancel();return
        if s['state']==2:self.finish(-25,'stage_hit_observed',s['frame']);return
        if not self.eligible(s):self.cancel();return
        p['last']=s['frame']
        if s['frame']-p['frame']>=45:
            # Survival plus room to maneuver; no damage reward or item pursuit incentive.
            edge=min(s['player'][0]-s['bounds'][0],s['bounds'][2]-s['player'][0])
            self.finish(float(2+np.clip(edge/48,0,2)), 'stage_safe_observation',s['frame'])

stage_learner=StageLearner()
