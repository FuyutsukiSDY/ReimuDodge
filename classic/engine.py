"""Receding-horizon planner with immediate-contact protection.
Native game coordinates; collision checks cover swept paths, not endpoints.
"""
import numpy as np
from enemies import enemy_hazards
from routes import guidance
from static_lasers import stationary, swept_static

ACTIONS = [(0,0,True)] + [(x,y,f) for f in (True,False)
    for x,y in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]]


def laser_clearance(points, lasers, times, radius):
    if not lasers:return np.full(len(points),1e5)
    t=np.asarray(times)[:,None]
    origin=np.array([l['origin'] for l in lasers])
    ov=np.array([l.get('origin_velocity',(0,0)) for l in lasers])
    angle=np.array([l['angle'] for l in lasers])+t*np.array([l.get('omega',0) for l in lasers])
    cosine,sine=np.cos(angle),np.sin(angle)
    start=np.maximum(0,np.array([l['start'] for l in lasers])+t*np.array([l.get('start_velocity',l['speed']) for l in lasers]))
    end=np.maximum(start,np.array([l['end'] for l in lasers])+t*np.array([l.get('end_velocity',l['speed']) for l in lasers]))
    dx=points[:,0,None]-origin[:,0]-t*ov[:,0]
    dy=points[:,1,None]-origin[:,1]-t*ov[:,1]
    along=np.clip(dx*cosine+dy*sine,start,end)
    dx-=along*cosine;dy-=along*sine
    d=np.sqrt(dx*dx+dy*dy)
    clearance=d-np.array([l['width'] for l in lasers])*.5-radius-2
    onset=np.array([l.get('danger_from',0) for l in lasers])
    expiry=np.array([l.get('danger_until',np.inf) for l in lasers])
    clearance=np.where((t>=onset)&(t<=expiry),clearance,1e5)
    return np.min(clearance,axis=1)




def swept(starts,velocity,duration,time,bullets,lasers,radius,margin):
    clearance=np.full(len(starts),1e4)
    if len(bullets):
        rx=starts[:,0,None]-(bullets[:,0]+bullets[:,2]*time)
        ry=starts[:,1,None]-(bullets[:,1]+bullets[:,3]*time)
        vx=velocity[:,0,None]-bullets[:,2]
        vy=velocity[:,1,None]-bullets[:,3]
        t=np.clip(-(rx*vx+ry*vy)/np.maximum(vx*vx+vy*vy,1e-9),0,duration)
        dx=rx+vx*t;dy=ry+vy*t
        d=np.sqrt(dx*dx+dy*dy)-bullets[None,:,4]-radius-margin
        clearance=np.min(d,axis=1)
    fixed=[l for l in lasers if stationary(l)]
    if fixed:
        clearance=np.minimum(clearance,swept_static(starts,velocity,duration,time,fixed,radius))
    lasers=[l for l in lasers if not stationary(l)]
    if lasers:
        steps=np.linspace(0,duration,int(np.ceil(duration))+1)
        points=(starts[:,None,:]+velocity[:,None,:]*steps[None,:,None]).reshape(-1,2)
        times=np.tile(steps+time,len(starts))
        lc=laser_clearance(points,lasers,times,radius).reshape(len(starts),-1).min(axis=1)
        clearance=np.minimum(clearance,lc)
    return clearance


def _plan(player, bullets, lasers, speeds, radius=1.25, previous=0,
         depth=7, width=12, chunk=6, enemies=(), bounds=(8,16,376,432), route_override=None,corner_escape=False,safety_margin=0,reserve_space=False,laser_position=False,mixed_retreat=False,laser_options=False):
    # Only stage 5 and stage 6 waves made entirely of small/knife bullets.
    # Mixed large-orb and laser scenes keep the established search unchanged.
    corridor_search=not lasers and (reserve_space or (mixed_retreat and
        len(bullets)>=120 and all(b[4]<=7 for b in bullets)))
    reserve_space=reserve_space or (mixed_retreat and not lasers and len(enemies)==1 and len(bullets)>=48 and sum(b[4]>=10 for b in bullets)>=12)
    if reserve_space:safety_margin=0
    # Classic stage 5/6 only: retain extra alternatives without the cost
    # of doubling the beam in dense waves. Earlier stages keep their budget.
    if corridor_search:
        width=max(width,16)
    p=np.asarray(player,float)
    xmin,top,xmax,bottom=bounds
    ymin=top  # Keep the upper escape route available when the lower field closes.
    velocities=np.array([(x*(speeds[3 if f else 2] if x and y else speeds[1 if f else 0]),
                           y*(speeds[3 if f else 2] if x and y else speeds[1 if f else 0])) for x,y,f in ACTIONS])
    bullets=np.asarray(bullets,float).reshape(-1,5)
    guide=route_override if route_override is not None else guidance(p,bullets,lasers,enemies,bounds)
    # Warning-phase room is scored over every reachable path, never a fixed waypoint.
    pocket_lasers=[]
    if guide is None and lasers and all(stationary(l) for l in lasers):
        warning=[l for l in lasers if 0<l.get('danger_from',0)<=60]
        if warning:
            pocket_lasers=[dict(l,danger_from=0,danger_until=1e9) for l in lasers
                           if l.get('danger_until',0)>0]
    if guide is None and lasers and all(stationary(l) for l in lasers):
        width=max(width,28 if laser_options and {l.get('warmup') for l in lasers}=={60,76,92} else 20)
    follow=None
    if (guide is None and len(enemies)==1 and lasers and all(stationary(l) for l in lasers)
            and {l.get('warmup') for l in lasers}=={60,76,92}
            and all(not l.get('firing',False) for l in lasers)):
        boss=np.asarray(enemies,float).reshape(-1,6)[0]
        follow=float(np.clip(boss[0],xmin+48,xmax-48))
    tactical=(guide is None and not lasers and len(enemies)==1 and len(bullets)>=24 and
              np.count_nonzero((np.abs(bullets[:,4]-16)<.01)&
                               (np.linalg.norm(bullets[:,2:4],axis=1)>=6))>=2)
    keep_retreat=guide is None and not lasers and len(enemies)>=3 and len(bullets)>=24
    fast_actions=np.array([not focus for _,_,focus in ACTIONS])
    bodies=enemy_hazards(enemies)
    if len(bodies):bullets=np.concatenate((bullets,bodies))
    # Prefer staying within a roomy static-laser pocket, but never forbid escape.
    settle=(guide is None and bool(lasers) and all(
        stationary(l) and l.get('firing',False) and
        l.get('danger_from',0)<=0 and l.get('danger_until',0)>=35
        for l in lasers))
    if settle:
        settle=swept(p[None,:],np.zeros((1,2)),35,0,bullets,lasers,radius,0)[0]>=24
    durations=[min(2 if layer==0 else 3,chunk) if layer<2 else chunk for layer in range(depth)]
    horizon=sum(durations)
    exit_bullets=bullets
    if len(bullets):
        reach_horizon=horizon
        reach=np.linalg.norm(bullets[:,2:4],axis=1)*(reach_horizon+2)+max(speeds)*reach_horizon+bullets[:,4]+10
        bullets=bullets[np.linalg.norm(bullets[:,:2]-p,axis=1)<reach]
    # Protect the first three commanded frames under both immediate input and
    # a two-frame delay continuing the PREVIOUS direction. Include t=0.
    starts=np.repeat(p[None,:],len(ACTIONS),axis=0)
    urgent=swept(starts,velocities,3,0,bullets,[l for l in lasers if l.get('firing',False) or 'danger_from' in l],radius,.25)
    delayed=swept(np.clip(starts+velocities[previous]*2,[xmin,top],[xmax,bottom]),velocities,3,2,bullets,[l for l in lasers if l.get('firing',False) or 'danger_from' in l],radius,.25)
    middle=swept(np.clip(starts+velocities[previous],[xmin,top],[xmax,bottom]),velocities,3,1,bullets,[l for l in lasers if l.get('firing',False) or 'danger_from' in l],radius,.25)
    urgent=np.minimum(np.minimum(urgent,delayed),middle)
    immediate_end=starts+velocities*3
    immediate_valid=(immediate_end[:,0]>=xmin)&(immediate_end[:,0]<=xmax)&(immediate_end[:,1]>=ymin)&(immediate_end[:,1]<=bottom)
    poses=p[None,:];costs=np.zeros(1);first=np.array([-1]);paths=np.empty((1,0,2))
    survival=np.full(1,1e6);minimums=np.full(1,1e6);elapsed=0
    for layer,duration in enumerate(durations):
        n=len(poses);starts=np.repeat(poses,len(ACTIONS),axis=0)
        velocity=np.tile(velocities,(n,1));actions=np.tile(np.arange(len(ACTIONS)),n)
        ends=starts+velocity*duration
        roots=actions if layer==0 else np.repeat(first,len(ACTIONS))
        # All future layers are on the same clock; never skip the current pose.
        clearance=swept(starts,velocity,duration,elapsed,bullets,lasers,radius,.6)
        path_min=np.minimum(np.repeat(minimums,len(ACTIONS)),clearance)
        comfortable=clearance-(.6+elapsed*.018)
        invalid=(ends[:,0]<xmin)|(ends[:,0]>xmax)|(ends[:,1]<ymin)|(ends[:,1]>bottom)
        hit=np.repeat(survival,len(ACTIONS))
        hit=np.minimum(hit,np.where(clearance<0,elapsed+duration,1e6))
        # If at least one immediate action is safe, no distant cost may override it.
        immediate=urgent[roots]
        # If no route preserves the comfort margin, still protect routes with
        # actual non-contact clearance before accepting a predicted hit.
        threshold=0 if np.any((urgent>=0)&immediate_valid) else -.25
        safe=(urgent>=threshold)&immediate_valid
        disallowed=(immediate<threshold) if np.any(safe) else np.zeros(len(ends),bool)
        penalty=np.where(clearance<0,1e5+np.minimum(-clearance,100)*1000,0)
        penalty+=invalid*1e8
        penalty+=np.exp(-np.clip(comfortable,-10,200)/7)*4
        penalty+=np.linalg.norm(ends-starts,axis=1)*.003
        # Smooth edge pressure retains retreat space without banning edge escapes.
        edge=np.minimum(ends[:,0]-xmin,xmax-ends[:,0])
        penalty+=np.maximum(0,64-edge)**2*.002
        if not guide or guide['mode']!='cross':
            penalty+=np.maximum(0,ends[:,1]-396)**2*.003
        if corner_escape and guide is None and not lasers and len(bullets)>=20:
            # Earlier soft pressure out of bottom corners, never a hard wall.
            penalty+=np.maximum(0,96-edge)*np.maximum(0,ends[:,1]-(bottom-96))*.002
        if mixed_retreat and reserve_space and not lasers and np.count_nonzero((bullets[:,4]>=20)&(np.linalg.norm(bullets[:,2:4],axis=1)>=6))>=2:
            penalty+=np.maximum(0,96-edge)**2*.012
        if reserve_space and not lasers:
            if corridor_search:penalty+=np.maximum(0,96-edge)**2*.006
            # Soft cost reserves downward escape space; never forbids the bottom.
            penalty+=np.maximum(0,ends[:,1]-(bottom-72))**2*.012
        if keep_retreat:
            # In multi-enemy waves, reserve room behind the player before the
            # final rows become a trap. This is a cost, never a forbidden zone.
            retreat=np.maximum(0,ends[:,1]-(bottom-60))
            penalty+=retreat**2*.012*(1+np.maximum(0,64-edge)/64)
            # Preserve a lateral exit before a multi-enemy wave closes in.
            # Bottom-only pressure can merely move the trap to a lower corner.
            penalty+=np.maximum(0,96-edge)**2*.012
        if settle:
            penalty+=np.linalg.norm(ends-p,axis=1)*.04
        if laser_position and follow is not None:
            # Only the recognized stationary warning pattern; collision and
            # survival ranking remain dominant over this positioning cost.
            penalty+=np.abs(ends[:,0]-follow)*.035
        if pocket_lasers and layer==depth-1:
            room=laser_clearance(ends,pocket_lasers,np.zeros(len(ends)),radius)
            penalty+=np.maximum(0,18-room)**2*.01
        if guide:
            penalty+=np.linalg.norm(ends-np.array(guide['target']),axis=1)*guide['weight']
            if guide['mode'] in ('chase','stream'):
                # Cruise in focus mode while the path has ample clearance.
                # Fade this preference near hazards; never exclude fast escapes.
                fast=fast_actions[actions]
                penalty+=fast*duration*2.0*np.clip((clearance-8)/16,0,1)
            if guide['mode']=='stream':
                # Staying still may be safe against existing bullets but invites
                # the next aimed volley. Prefer lateral progress in open space.
                lateral=np.array([x for x,y,f in ACTIONS])[actions]
                penalty+=(lateral==0)*duration*.8*np.clip((clearance-(16 if reserve_space else 4))/12,0,1)
        else:
            penalty+=np.maximum(0,300-ends[:,1])*.025
        penalty+=abs(ends[:,0]-192)*.0008
        if layer==0:penalty+=(actions!=previous)*.10
        total=np.repeat(costs,len(ACTIONS))+penalty
        # Boundary and first-step safety dominate. Among doomed predictions,
        # preserve more survival time instead of choosing fewer total collisions.
        rank_survival=np.where(invalid,-1,hit)
        if not np.any(safe):rank_survival=np.where(invalid,-1,hit)+np.clip(immediate,-100,0)*.01
        # Among equally surviving paths, prefer a small clearance reserve.
        # Never let this preference override immediate collision protection.
        order=(np.lexsort((total,np.maximum(0,safety_margin-path_min),-rank_survival,disallowed))
               if safety_margin>0 else np.lexsort((total,-rank_survival,disallowed)))
        if follow is not None and layer==depth-1:
            best=order[0]
            equivalent=(total<=total[best]+1)&(rank_survival==rank_survival[best])
            equivalent&=(disallowed==disallowed[best])&(path_min>=path_min[best])
            equivalent&=(urgent[roots]>=urgent[roots[best]])
            equivalent&=(np.linalg.norm(ends-ends[best],axis=1)<=12)
            options=np.flatnonzero(equivalent)
            if len(options):
                nearest=options[np.lexsort((total[options],np.abs(ends[options,0]-follow)))[0]]
                order=np.concatenate(([nearest],order[order!=nearest]))
        picked=[];seen=set()
        for idx in order:
            cell=tuple(np.round(ends[idx]/(6 if (tactical or corridor_search) and not lasers and layer>=2 else 3)).astype(int))
            # In Classic stage 5/6, keep distinct distant corridors instead
            # of filling the beam with adjacent endpoints. First steps stay fine.
            if cell in seen:continue
            seen.add(cell);picked.append(idx)
            if len(picked)==width:break
        picked=np.array(picked)
        parent_paths=np.repeat(paths,len(ACTIONS),axis=0)
        paths=np.concatenate((parent_paths[picked],ends[picked,None,:]),axis=1)
        poses,costs,first=ends[picked],total[picked],roots[picked]
        minimums=path_min[picked]
        survival=rank_survival[picked]
        elapsed+=duration
    if tactical and not lasers and np.count_nonzero((np.abs(bullets[:,4]-16)<.01)&(np.linalg.norm(bullets[:,2:4],axis=1)>=6.7))>=2:
        # Count safe next directions so the chosen endpoint retains exits.
        next_starts=np.repeat(poses,len(ACTIONS),axis=0)
        next_v=np.tile(velocities,(len(poses),1))
        next_ends=next_starts+next_v*6
        within=np.all(next_ends>=[xmin,top],axis=1)&np.all(next_ends<=[xmax,bottom],axis=1)
        clear=swept(next_starts,next_v,6,horizon,exit_bullets,lasers,radius,.6)
        available=((clear>=1)&within).reshape(len(poses),len(ACTIONS))
        # Focus/fast versions of one direction count as a single exit.
        exits=np.count_nonzero(available[:,1:9]|available[:,9:17],axis=1)
        costs+=8/(1+exits)
        denied=(urgent[first]<threshold) if np.any(safe) else np.zeros(len(first),bool)
        final=np.lexsort((costs,-survival,denied))[0]
        return int(first[final]),paths[final],float(costs[final])
    return int(first[0]),paths[0],float(costs[0])


def plan(player, bullets, lasers, speeds, radius=1.25, previous=0,
         depth=7, width=12, chunk=6, enemies=(), bounds=(8,16,376,432), route_override=None,corner_escape=False,safety_margin=0,reserve_space=False,laser_position=False,mixed_retreat=False,laser_options=False):
    args=(player,bullets,lasers,speeds,radius,previous)
    kw=dict(depth=depth,width=width,chunk=chunk,enemies=enemies,bounds=bounds,route_override=route_override,safety_margin=safety_margin,reserve_space=reserve_space,laser_position=laser_position,mixed_retreat=mixed_retreat,laser_options=laser_options)
    baseline=_plan(*args,**kw)
    xmin,top,xmax,bottom=bounds
    if not corner_escape or lasers or route_override or len(bullets)<20 or player[1]<bottom-96 or min(player[0]-xmin,xmax-player[0])>96:
        return baseline
    hazards=np.concatenate((np.asarray(bullets,float).reshape(-1,5),enemy_hazards(enemies)))
    def velocity(a):
        x,y,f=ACTIONS[a]
        speed=speeds[3 if f else 2] if x and y else speeds[1 if f else 0]
        return np.array([x*speed,y*speed])
    def urgent_gap(a):
        v=velocity(a)[None,:];p=np.asarray(player,float)
        return min(float(swept(np.clip(p+velocity(previous)*delay,[xmin,top],[xmax,bottom])[None,:],v,3,delay,hazards,lasers,radius,.25)[0]) for delay in (0,1,2))
    old_gap=urgent_gap(baseline[0])
    # Reposition early, never while the baseline already needs a tight escape.
    if old_gap<6:return baseline
    candidate=_plan(*args,**kw,corner_escape=True)
    if candidate[0]==baseline[0]:return baseline
    if urgent_gap(candidate[0])<max(6,old_gap-2):return baseline
    durations=[min(2 if layer==0 else 3,chunk) if layer<2 else chunk for layer in range(depth)]
    def path_gap(path):
        starts=np.vstack((player,path[:-1]));elapsed=0;result=1e6
        for start,end,duration in zip(starts,path,durations):
            result=min(result,float(swept(start[None,:],((end-start)/duration)[None,:],duration,elapsed,hazards,lasers,radius,.6)[0]));elapsed+=duration
        return result
    if path_gap(candidate[1])<max(0,min(4,path_gap(baseline[1]))):return baseline
    return candidate
