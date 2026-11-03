"""Bounded empirical ranking of already-safe crossing candidates.
This is local experience scoring, not a learned collision model.
"""
import json,math
from pathlib import Path

class Learner:
    def __init__(self):
        self.enabled=False;self.path=None;self.data={};self.pending=None;self.dirty=False;self.error=None;self.last_result=None
    def configure(self,path):
        self.path=Path(path)
        try:
            obj=json.loads(self.path.read_text(encoding='utf8')) if self.path.exists() else {}
            if obj and obj.get('version')!=1:raise ValueError('经验文件版本不匹配')
            data=obj.get('scores',{})
            if not isinstance(data,dict) or len(data)>10000:raise ValueError('经验文件格式异常')
            for k,v in data.items():
                if not isinstance(k,str) or not isinstance(v,dict) or not isinstance(v.get('n'),int) or not 0<v['n']<=1000000 or not math.isfinite(v.get('mean',float('nan'))) or not -30<=v['mean']<=10:
                    raise ValueError('经验样本无效')
            self.data=data
        except Exception as e:self.data={};self.error=str(e)
    def context(self,s,b):
        g=s.get('game') or {}
        return '|'.join(str(x) for x in (g.get('stage'),g.get('difficulty'),g.get('character'),g.get('shot'),
                b.get('phase_start_hp'),b.get('limit_frames'),int(b.get('timer_frames',0)//180),int(s.get('power',0)//8),
                int(s['player'][1]//80),1 if b['pos'][0]>s['player'][0] else -1))
    def key(self,s,b,rise,focus):return self.context(s,b)+'|'+str(rise)+'|'+str(int(focus))
    def bias(self,s,b,rise,focus):
        if not self.enabled:return 0.
        value=self.data.get(self.key(s,b,rise,focus))
        if not value:return 0.
        # Two observations minimum; even strong history cannot waive safety.
        if value['n']<2:return 0.
        return max(-8.,min(8.,value['mean']*min(1.,value['n']/5)))
    def cancel(self):self.pending=None
    def begin(self,s,info):
        if not self.enabled or self.pending or info.get('reason')!='up_then_across':return
        b=next((b for b in s.get('bosses',[]) if b.get('damageable')),None)
        if b is None or s['state']!=0 or s.get('invincible') or s.get('bomb_active'):return
        self.pending=dict(key=self.key(s,b,info['rise'],not info['fast']),slot=b['slot'],phase=b.get('first_observed_frame'),
            frame=s['frame'],last=s['frame'],hp=b['hp'],start_hp=max(1,b['hp']),damage=0,bombs=s['bombs'])
    def finish(self,reward,reason,frame):
        p=self.pending
        if not p:return
        v=self.data.setdefault(p['key'],dict(n=0,mean=0.))
        v['n']+=1;v['mean']+=(reward-v['mean'])/min(v['n'],20)
        self.last_result=dict(reason=reason,reward=reward,frames=frame-p['frame'],damage=p['damage'],samples=v['n'])
        self.pending=None;self.dirty=True
    def observe(self,s):
        p=self.pending
        if not self.enabled or not p:return
        frame=s['frame'];dt=frame-p['last']
        if dt<0 or dt>12 or s.get('invincible') or s.get('bomb_active') or s.get('bombs')!=p['bombs']:
            self.cancel();return
        if s['state']==2:self.finish(-25.,'hit_observed',frame);return
        if s['state']!=0:self.cancel();return
        b=next((b for b in s.get('bosses',[]) if b['slot']==p['slot'] and b.get('first_observed_frame')==p['phase']),None)
        if b is None:self.cancel();return  # Never interpret disappearance as a kill.
        if b['hp']>p['hp']:self.cancel();return
        p['damage']+=max(0,p['hp']-b['hp']);p['hp']=b['hp'];p['last']=frame
        if frame-p['frame']>=120:
            self.finish(min(10.,p['damage']/p['start_hp']*50)-1.,'two_second_observation',frame)
    def save(self):
        if not self.dirty or self.path is None:return
        try:
            tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(dict(version=1,scores=self.data),ensure_ascii=False),encoding='utf8')
            tmp.replace(self.path);self.dirty=False;self.error=None
        except OSError as e:self.error=str(e)
    def status(self):
        return dict(enabled=self.enabled,contexts=len(self.data),samples=sum(v['n'] for v in self.data.values()),pending=bool(self.pending),last_result=self.last_result,error=self.error)

learner=Learner()
