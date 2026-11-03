"""New edition only: verified y<128, item mode 1 persists after retreat.
Predict current hazards only; revalidate on every observation.
"""
import numpy as np
from engine import ACTIONS, swept
from enemies import enemy_hazards

class Collector:
    def __init__(self): self.reset()
    def reset(self):
        self.phase=None;self.last=-1;self.cooldown=-1;self.born=0;self.home=300
    def choose(self,s,previous,baseline,enabled):
        frame=s['frame'];p=np.asarray(s['player'],float)
        if frame<self.last or frame-self.last>90:self.reset()
        self.last=frame
        info={'phase':self.phase or 'idle','reason':'not_needed'}
        s['autocollect']=info
        def stop(reason):
            active=self.phase is not None
            self.phase=None
            if active:self.cooldown=frame+(8 if reason=='corridor_blocked' else 20)
            info.update(reason=reason,phase='aborted')
            return (baseline,dict(active=False,autocollect=info)) if active else None
        if not enabled:return stop('disabled')
        if (s.get('power') is None or s.get('pickup_error') or s['state']!=0
            or s.get('bomb_active') or s['lasers'] or s.get('bosses') or baseline[2]>=1000):
            return stop('boss_present' if s.get('bosses') else 'laser_present' if s['lasers'] else 'danger_state')
        route=s.get('route') or {}
        if route.get('mode') not in (None,'stream'):return stop('authored_route')
        items=s.get('collection_items',[])
        eligible=[it for it in items if (it['kind'] in (0,2,4) and s['power']<128)
                  or (it['kind']==3 and 0<=s.get('bombs',-1)<7)]
        speed=float(s['speeds'][0])
        if speed<=0:return stop('unknown_speed')
        if self.phase is None:
            if frame<self.cooldown:
                info.update(reason='cooldown',remaining=self.cooldown-frame);return None
            eta=max(0,(p[1]-120)/speed)+2
            eligible=[it for it in eligible if it.get('mode',0)==0 and it['pos'][1]+max(0,it['velocity'][1])*eta<430]
            value=sum(8 if it['kind'] in (2,3,4) else 1 for it in eligible)
            info.update(value=value,eligible=len(eligible))
            if value<3:info['reason']='insufficient_items';return None
            if not 128<=p[1]<=420 or not 48<=p[0]<=336:info['reason']='starting_position';return None
            self.phase='ascending';self.home=float(np.clip(p[1],260,360));self.born=frame
        if frame-self.born>210:return stop('timeout')
        attracted=sum(it.get('mode',0)==1 for it in eligible)
        # Mode 1 also occurs for nearby individual items. Only crossing
        # the verified line confirms the global collection transition.
        if self.phase=='ascending' and p[1]<128:self.phase='returning'
        if self.phase=='ascending' and not eligible:return stop('items_gone')
        if self.phase=='returning' and p[1]>=self.home-4:
            self.phase=None;self.cooldown=frame+90;info.update(phase='complete',reason='returned');return None
        hazards=np.concatenate((np.asarray(s['bullets'],float).reshape(-1,5),enemy_hazards(s['enemies'])))
        def gap(at,v,d,t):return float(swept(at[None,:],v[None,:],max(d,.01),t,hazards,[],s['radius'],1)[0])
        target=120 if self.phase=='ascending' else self.home
        sign=1 if target>p[1] else -1
        v=np.array([0.,sign*speed]);duration=abs(target-p[1])/speed
        end=np.array([p[0],target]);minimum=gap(p,v,duration,0)
        elapsed=duration
        if self.phase=='ascending':
            minimum=min(minimum,gap(end,np.zeros(2),2,elapsed));elapsed+=2
            back=(self.home-target)/speed
            minimum=min(minimum,gap(end,np.array([0.,speed]),back,elapsed));elapsed+=back
            end=np.array([p[0],self.home])
        minimum=min(minimum,gap(end,np.zeros(2),12,elapsed))
        x,y,f=ACTIONS[previous];old_speed=s['speeds'][3 if f else 2] if x and y else s['speeds'][1 if f else 0]
        old=np.array([x,y])*old_speed
        minimum=min(minimum,gap(p,old,2,0),gap(p+old*2,v,min(3,duration),2))
        if minimum<20:return stop('corridor_blocked')
        # Execute only the next short action, not the predicted complete journey.
        action=11 if sign<0 else 12
        path=[];at=p.copy()
        for dt in (2,3,6,6,6,6,6):
            at=at+v*min(dt,abs(target-at[1])/speed);path.append(at.copy())
        info.update(phase=self.phase,reason='clear_corridor',clearance=minimum,attracted=attracted,target=[float(p[0]),target])
        return (action,np.asarray(path),baseline[2]),dict(active=True,autocollect=info,target=info['target'])

controller=Collector()
