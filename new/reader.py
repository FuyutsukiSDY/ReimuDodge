from boss_telemetry import decode as decode_bosses
"""Only PROCESS_VM_READ and PROCESS_QUERY_INFORMATION are requested."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import hashlib
import struct
import numpy as np
from enemies import EnemyTracker, POOL_RVA, COUNT, STRIDE
from lasers import LaserTracker, exposure_window

SHA='48630a42a2eb6762d0db2a7e0d151203efbe67220fef7d2f9d0d51857928ac82'
k=C.WinDLL('kernel32',use_last_error=True);ps=C.WinDLL('psapi',use_last_error=True)
k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
k.CloseHandle.argtypes=[W.HANDLE]
k.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
ps.EnumProcesses.argtypes=[C.POINTER(W.DWORD),W.DWORD,C.POINTER(W.DWORD)]
ps.EnumProcessModulesEx.argtypes=[W.HANDLE,C.POINTER(C.c_void_p),W.DWORD,C.POINTER(W.DWORD),W.DWORD]

def require(ok,label):
    if not ok:raise RuntimeError(f'{label} (Windows {C.get_last_error()})')

class SnapshotNotReady(RuntimeError):
    """A full snapshot must be reread; never plan using a partial hazard set."""
    def __init__(self,details):
        super().__init__('敌弹数据暂时不完整')
        self.details=details

class Reader:
    def __init__(self):
        self.h=None
        self.enemy_tracker=EnemyTracker()
        self.laser_tracker=LaserTracker()
        ids=(W.DWORD*4096)();n=W.DWORD()
        require(ps.EnumProcesses(ids,C.sizeof(ids),C.byref(n)),'无法枚举进程')
        found=[]
        for pid in ids[:n.value//4]:
            h=k.OpenProcess(0x1000,False,pid)
            if not h:continue
            try:
                b=C.create_unicode_buffer(32768);size=W.DWORD(len(b))
                if k.QueryFullProcessImageNameW(h,0,b,C.byref(size)) and Path(b.value).name.lower()=='th06nc.exe':found.append((pid,Path(b.value)))
            finally:k.CloseHandle(h)
        if len(found)!=1:raise RuntimeError('请启动且只保留一个 th06nc 游戏进程')
        self.pid,path=found[0]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=SHA:raise RuntimeError('游戏版本不匹配，需要重新适配')
        self.h=k.OpenProcess(0x410,False,self.pid)
        require(self.h,'无法只读连接游戏')
        try:
            modules=(C.c_void_p*1024)();n=W.DWORD()
            require(ps.EnumProcessModulesEx(self.h,modules,C.sizeof(modules),C.byref(n),3),'无法定位游戏模块')
            self.base=modules[0]
            # Verify executable identity independently of the invincibility patch.
            if self.read(0x10fa0,8)!=bytes.fromhex('488bc45341544157'):raise RuntimeError('运行代码校验失败')
        except Exception:
            self.close();raise

    def close(self):
        if self.h:k.CloseHandle(self.h);self.h=None

    def read(self,rva,n):
        b=C.create_string_buffer(n);got=C.c_size_t()
        require(k.ReadProcessMemory(self.h,self.base+rva,b,n,C.byref(got)) and got.value==n,'读取失败，游戏可能已退出')
        return b.raw

    def snapshot(self):
        # One read contains the pool, lasers and frame counter to reduce skew.
        raw=self.read(0x436ef0,0xff900)
        frame=struct.unpack_from('<I',raw,4)[0]
        enemy_raw=self.read(POOL_RVA,COUNT*STRIDE)
        enemies=self.enemy_tracker.update(enemy_raw,frame)
        bosses=decode_bosses(enemy_raw)
        pool=memoryview(raw)[8:8+640*0x620]
        state=np.ndarray((640,),'<u2',pool,0x44,(0x620,))
        pos=np.ndarray((640,2),'<f4',pool,0x30,(0x620,4))
        vel=np.ndarray((640,2),'<f4',pool,8,(0x620,4))
        dims=np.ndarray((640,2),'<f4',pool,0x5f4,(0x620,4))
        active=(state>=1)&(state<=4)
        valid=np.isfinite(pos).all(axis=1)&np.isfinite(vel).all(axis=1)&np.isfinite(dims).all(axis=1)
        valid&=(abs(pos)<5000).all(axis=1)&(abs(vel)<100).all(axis=1)&(dims>0).all(axis=1)&(dims<512).all(axis=1)
        if np.any(active&~valid):
            indices=np.flatnonzero(active&~valid)
            # Strings preserve NaN/Inf evidence without writing invalid JSON.
            details=dict(frame=frame,count=len(indices),bullets=[dict(slot=int(i),state=int(state[i]),
                pos=[repr(float(v)) for v in pos[i]],vel=[repr(float(v)) for v in vel[i]],
                dims=[repr(float(v)) for v in dims[i]]) for i in indices[:8]])
            raise SnapshotNotReady(details)
        mask=active&valid
        bullets=np.column_stack((pos[mask],vel[mask],np.min(dims[mask],axis=1)*.5)).astype(float)
        lasers=[]
        for i in range(64):
            o=0xf502c+i*0x298
            if not raw[o+0x260] or raw[o+0x27c] not in (0,1):continue
            start,end=struct.unpack_from('<2f',raw,o-4)
            width=struct.unpack_from('<f',raw,o-16)[0]
            angle=struct.unpack_from('<f',raw,o+0x24c)[0]
            origin=struct.unpack_from('<2f',raw,o+0x264)
            speed=struct.unpack_from('<f',raw,o+0x258)[0]
            if not np.isfinite([start,end,width,angle,*origin,speed]).all():raise RuntimeError('激光数据异常')
            if end<=start or width<=0:continue
            phase=raw[o+0x27c]
            counter=struct.unpack_from('<i',raw,o-8)[0]
            warmup=struct.unpack_from('<i',raw,o+0x25c)[0]
            duration=struct.unpack_from('<i',raw,o+0x254)[0]
            lasers.append(dict(slot=i,origin=origin,start=start,end=end,width=width,angle=angle,speed=speed,
                firing=phase==1,phase_counter=counter,warmup=warmup,duration=duration,
                **exposure_window(phase,counter,warmup,duration)))
        lasers=self.laser_tracker.update(lasers,frame)
        player=self.read(0x549ff0+0x7710,0x194)
        p=struct.unpack_from('<2f',player,0x20)
        speeds=struct.unpack_from('<4f',player,0x150)
        scale=struct.unpack_from('<2f',player,0)
        radius=struct.unpack_from('<f',player,0x3c)[0]
        if not np.isfinite([*p,*speeds,radius]).all() or not (0<radius<20) or not all(0<s<20 for s in speeds):raise SnapshotNotReady(dict(kind='player',frame=frame,player=list(p),speeds=list(speeds),radius=radius))
        # Actual movement multipliers may change during scripted sequences.
        if not all(.9<s<1.1 for s in scale):raise RuntimeError('自机处于特殊移动状态，请稍后启动')
        bx,by,bw,bh=struct.unpack('<4f',self.read(0x549d30,16))
        if not np.isfinite([bx,by,bw,bh]).all() or not (0<=bx<384 and 0<=by<448 and 0<bw<=384 and 0<bh<=448):raise RuntimeError('移动边界数据异常')
        bounds=(bx,by,bx+bw,by+bh)
        cheat=self.read(0x6c1ac,2)!=bytes.fromhex('7507') or self.read(0x6c3f4,6)!=bytes.fromhex('0f86df000000')
        bombs=struct.unpack('<b',self.read(0x549d41,1))[0]
        bomb_active=bool(self.read(0x553eb8,1)[0])
        death_window=struct.unpack_from('<i',player,0x2c)[0]
        return dict(bosses=bosses,frame=frame,player=p,speeds=speeds,radius=radius,bullets=bullets,
                    lasers=lasers,enemies=enemies,bounds=bounds,state=player[0x188],invincible=cheat,
                    bombs=bombs,bomb_active=bomb_active,death_window=death_window)
