"""New-edition read-only boss telemetry. Never infer every removal is a kill."""
import struct

def decode(raw,stride=0x10b0,count=256):
    bosses=[]
    for slot in range(count):
        o=slot*stride;flags=raw[o+0xbc:o+0xbf]
        if not flags[0]&128 or not flags[1]&8:continue
        hp,maximum,phase_start=struct.unpack_from('<3i',raw,o+0x234)
        timer=struct.unpack_from('<i',raw,o+4)[0]
        limit=struct.unpack_from('<i',raw,o+0xc54)[0]
        threshold=struct.unpack_from('<i',raw,o+0xa0)[0]
        if not (-100000<=hp<=10000000 and 0<=maximum<=10000000 and -1<=limit<=10000000):continue
        bosses.append(dict(slot=slot,hp=hp,max_hp=maximum,phase_start_hp=phase_start,
            timer_frames=timer,limit_frames=limit,remaining_frames=max(0,limit-timer) if limit>=0 else None,
            damageable=bool(flags[1]&16),script_id=struct.unpack_from('<h',raw,o+0x80)[0],
            threshold_hp=threshold,pos=list(struct.unpack_from('<2f',raw,o+0xb0))))
    return bosses

class Tracker:
    def __init__(self):self.reset()
    def reset(self):self.previous={};self.frame=None;self.stage=None;self.pid=None
    def update(self,s,pid):
        frame=s['frame'];stage=(s.get('game') or {}).get('stage');events=[]
        if self.pid!=pid or self.stage!=stage or (self.frame is not None and frame<self.frame):self.reset()
        if frame==self.frame:return events
        current={b['slot']:dict(b) for b in s.get('bosses',[])}
        for slot,old in self.previous.items():
            b=current.get(slot)
            changed=b is None or b['timer_frames']<old['timer_frames'] or b['max_hp']!=old['max_hp'] or (b['hp']>old['hp'] and b['script_id']!=old['script_id'])
            if not changed:continue
            gap=frame-self.frame
            outcome='unconfirmed'
            if old['hp']<=0:outcome='zero_hp_observed'
            elif old['limit_frames']>=0 and old['timer_frames']>=old['limit_frames']:outcome='timeout_observed'
            elif 0<gap<=6 and old['limit_frames']>=0 and 0<=old['limit_frames']-old['timer_frames']<=gap:outcome='timeout_possible'
            events.append(dict(event='boss_phase_end',slot=slot,stage=stage,outcome=outcome,
                last_hp=old['hp'],max_hp=old['max_hp'],last_timer_frames=old['timer_frames'],
                observed_damage=old.get('observed_damage',0),first_observed_frame=old['first_observed_frame'],
                end_frame_interval=[self.frame,frame],last_elapsed_game_seconds=old['timer_frames']/60,
                partial_start=old['partial_start']))
            if b is not None:b['new_phase']=True
        for slot,b in current.items():
            old=self.previous.get(slot)
            if old is None or b.pop('new_phase',False):
                b.update(first_observed_frame=frame,observed_damage=0,partial_start=b['timer_frames']>2)
                events.append(dict(event='boss_phase_start',frame=frame,stage=stage,**b))
            else:
                b.update(first_observed_frame=old['first_observed_frame'],partial_start=old['partial_start'],
                    observed_damage=old['observed_damage']+max(0,old['hp']-b['hp']))
        s['bosses']=list(current.values())
        self.previous=current;self.frame=frame;self.stage=stage;self.pid=pid
        return events
