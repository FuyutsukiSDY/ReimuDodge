"""Track motion by laser pool slot; never infer motion across resets/teleports."""
import math

class LaserTracker:
    def __init__(self):
        self.frame=None
        self.previous={}
        self.history={}

    def update(self,lasers,frame):
        dt=frame-self.frame if self.frame is not None else 0
        result=[]
        histories={}
        if dt<0 or dt>12:self.history={}
        for index,source in enumerate(lasers):
            laser=dict(source)
            slot=laser.get('slot',index)
            old=self.previous.get(slot)
            history=self.history.get(slot,[])
            if old and dt>0:
                jump=math.hypot(*(a-b for a,b in zip(laser['origin'],old['origin'])))/dt
                turn=abs(math.remainder(laser['angle']-old['angle'],2*math.pi))/dt
                if (jump>12 or turn>.12 or laser['firing']!=old['firing']
                        or abs(laser['width']-old['width'])>=.01):
                    history=[]
            prior=[(f,l) for f,l in history if f<frame]
            if prior:
                mature=[item for item in prior if frame-item[0]>=3]
                anchor_frame,anchor=(mature[-1] if mature else prior[0])
            else:anchor_frame,anchor=frame,None
            estimate_dt=frame-anchor_frame
            if anchor is not None and not (0<estimate_dt<=12):anchor=None

            if old and dt==0 and all(laser[k]==old[k] for k in ('origin','angle','start','end','width','firing')):
                for k in ('omega','origin_velocity','start_velocity','end_velocity'):
                    if k in old:laser[k]=old[k]
            elif anchor and laser['firing']==anchor['firing'] and abs(laser['width']-anchor['width'])<.01:
                old=anchor;sample_dt=estimate_dt
                omega=math.remainder(laser['angle']-old['angle'],2*math.pi)/sample_dt
                v=[(a-b)/sample_dt for a,b in zip(laser['origin'],old['origin'])]
                lo=(laser['start']-old['start'])/sample_dt
                hi=(laser['end']-old['end'])/sample_dt
                # Large jumps may mean a reused slot or scripted teleport.
                if abs(omega)<=.12 and math.hypot(*v)<=12 and max(abs(lo),abs(hi))<=24:
                    laser.update(omega=omega,origin_velocity=v,start_velocity=lo,end_velocity=hi)
            # Pool reads can straddle a game frame. Estimate across at least
            # three frames instead of alternating zero and double velocity.
            valid_history=bool(anchor and 'omega' in laser)
            kept=prior if valid_history else []
            histories[slot]=[(f,l) for f,l in kept if frame-f<=6]+[(frame,dict(source))]
            result.append(laser)
        self.history=histories
        self.frame=frame
        self.previous={l.get('slot',i):dict(l) for i,l in enumerate(result)}
        return result


def exposure_window(phase,counter,warmup,duration):
    """Build 25306795: update at RVA 11ee1/11f7b/11fb8.
    Collision runs only in phase 1, including its final timer tick. Leave
    two extra frames at the end and start warnings one frame early to cover
    a read crossing the update. Invalid counters retain the old safe fallback.
    """
    if phase not in (0,1) or not all(0<=v<=10_000_000 for v in (counter,warmup,duration)):
        return {}
    if phase==1:return dict(danger_from=0,danger_until=max(0,duration-counter)+2)
    onset=max(0,warmup-counter-1)
    return dict(danger_from=onset,danger_until=onset+duration+3)
