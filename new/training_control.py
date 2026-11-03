"""Version-locked native transitions: practice mode 12, normal stage-load mode 3.
No heap snapshots or arbitrary ECL pointer rewinds.
"""
import struct
from invincibility import Trainer,nt,k
from game_state import read_state

class Training(Trainer):
    def __init__(self):super().__init__([])
    def close(self):
        if self.handle:k.CloseHandle(self.handle);self.handle=None
    def pause_context(self):
        node=struct.unpack('<Q',self.read(0x53c0b8,8))[0];seen=set()
        while node and node not in seen and len(seen)<128:
            if not 0x10000<=node<0x800000000000:break
            seen.add(node);b=self.read(node-self.base,64)
            if struct.unpack_from('<Q',b,8)[0]==self.base+0x9800:
                ctx=struct.unpack_from('<Q',b,56)[0]
                if not 0x10000<=ctx<0x800000000000:break
                return ctx-self.base+0x52d0
            node=struct.unpack_from('<Q',b,40)[0]
        raise ValueError('未找到游戏暂停菜单对象')
    def pause_ready(self):
        s=read_state(self)
        if s['mode']!=2 or s['frame']<2 or s['replay']:return False
        if s['paused']:return True
        ctx=self.pause_context()
        if struct.unpack('<i',self.read(ctx+0xd94,4))[0]!=0:
            raise ValueError('暂停菜单尚未复位')
        # State 0 builds the normal pause menu on the next game callback.
        self.write(0x53d400,b'\1')
        return True
    def request(self,stage=None):
        before=read_state(self)
        if not before['paused'] or before['mode']!=2 or before['replay']:
            raise ValueError('请先在普通流程或关卡练习中暂停；不接管 Replay')
        if self.read(0x53d405,1)!=b'\0':raise ValueError('符卡练习需使用专用重试入口，暂不通过此按钮跳关')
        target=before['stage'] if stage is None else int(stage)
        ctx=self.pause_context()
        if struct.unpack('<i',self.read(ctx+0xd94,4))[0]!=1:
            raise ValueError('请等待暂停菜单稳定后重试')
        if not 1<=target<=6 or before['difficulty'] not in (0,1,2,3):
            raise ValueError('当前支持普通 1–6 面，不接管 Extra')
        normal=not before['practice']
        requested_mode=3 if normal else 12
        stage_value=target-1 if normal else target
        checks={0xb4ae:bytes.fromhex('4488354b1f5300c705fd2ac6000c000000'),0x7bcd3:bytes.fromhex('ff0dfb0d4c00')}
        for addr,expected in checks.items():
            if self.read(addr,len(expected))!=expected:raise ValueError('游戏重开代码不匹配')
        if normal:
            checks.update({0x7be88:struct.pack('<I',0x7baaf),0x3c7bc:bytes.fromhex('418d5001895724')})
            for addr,expected in checks.items():
                if self.read(addr,len(expected))!=expected:raise ValueError('游戏切关代码不匹配')
        if nt.NtSuspendProcess(self.handle)<0:raise RuntimeError('无法同步游戏状态')
        changes=[]
        try:
            if read_state(self)!=before:raise ValueError('暂停状态发生变化，请重试')
            for addr,data in ((ctx+0xd94,struct.pack('<i',0)),(0x53cad4,struct.pack('<i',stage_value)),(0x53d400,b'\0'),(0xc6dfbc,struct.pack('<i',requested_mode))):
                changes.append((addr,self.read(addr,len(data))));self.write(addr,data)
        except Exception:
            for addr,data in reversed(changes):self.write(addr,data)
            raise
        finally:
            if nt.NtResumeProcess(self.handle)<0 and nt.NtResumeProcess(self.handle)<0:
                raise RuntimeError('恢复游戏失败，请重启游戏')
        return dict(previous=before,target_stage=target,transition_mode=requested_mode,resource_policy='carry_current' if normal else 'practice_defaults')
