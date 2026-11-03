"""Continuous capsule clearance for stationary beams during their active window."""
import numpy as np


def stationary(l):
    return (l.get('omega',0)==0 and
            all(v==0 for v in l.get('origin_velocity',(0,0))) and
            l.get('start_velocity',l['speed'])==0 and
            l.get('end_velocity',l['speed'])==0)


def swept_static(starts,velocity,duration,time,lasers,radius):
    origin=np.array([l['origin'] for l in lasers])
    angle=np.array([l['angle'] for l in lasers])
    cs,sn=np.cos(angle),np.sin(angle)
    lo=np.maximum(0,np.array([l['start'] for l in lasers]))
    hi=np.maximum(lo,np.array([l['end'] for l in lasers]))
    begin=np.maximum(0,np.array([l.get('danger_from',0) for l in lasers])-time)
    end=np.minimum(duration,np.array([l.get('danger_until',np.inf) for l in lasers])-time)
    active=(begin<=end)&(begin<=duration)&(end>=0)
    begin=np.clip(begin,0,duration);end=np.clip(end,0,duration)
    dx=starts[:,0,None]-origin[:,0];dy=starts[:,1,None]-origin[:,1]
    x=dx*cs+dy*sn;y=-dx*sn+dy*cs
    vx=velocity[:,0,None]*cs+velocity[:,1,None]*sn
    vy=-velocity[:,0,None]*sn+velocity[:,1,None]*cs
    # Segment/segment distance: endpoint projections plus an intersection test.
    xa=x+vx*begin;ya=y+vy*begin;xb=x+vx*end;yb=y+vy*end
    d2=np.minimum((xa-np.clip(xa,lo,hi))**2+ya**2,
                  (xb-np.clip(xb,lo,hi))**2+yb**2)
    speed2=np.maximum(vx*vx+vy*vy,1e-20)
    for endpoint in (lo,hi):
        t=np.clip(((endpoint-x)*vx-y*vy)/speed2,begin,end)
        d2=np.minimum(d2,(x+vx*t-endpoint)**2+(y+vy*t)**2)
    cross=np.divide(-y,vy,out=np.zeros_like(y),where=vy!=0)
    xc=x+vx*cross
    intersects=(vy!=0)&(cross>=begin)&(cross<=end)&(xc>=lo)&(xc<=hi)
    d2=np.where(intersects,0,d2)
    clearance=np.sqrt(d2)-np.array([l['width'] for l in lasers])*.5-radius-2
    return np.min(np.where(active,clearance,1e5),axis=1)
