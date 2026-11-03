"""Read-only state adapter and confirmed-menu normal/Extra alternation."""
import struct

def result_phase(r):
    node=struct.unpack('<Q',r.read(0x53c0b8,8))[0];seen=set()
    for _ in range(128):
        if not node or node in seen:return None
        if not 0x10000<=node<0x800000000000:raise ValueError('结算指针异常')
        seen.add(node);b=r.read(node-r.base,64)
        if struct.unpack_from('<Q',b,8)[0]==r.base+0x6fa70:
            ctx=struct.unpack_from('<Q',b,56)[0]
            if not 0x10000<=ctx<0x800000000000:raise ValueError('结算对象异常')
            phase=struct.unpack('<i',r.read(ctx-r.base+0x9e94,4))[0]
            return phase if 0<=phase<=17 else None
        node=struct.unpack_from('<Q',b,40)[0]
    return None

def read_state(r):
    def integer(a):return struct.unpack('<i',r.read(a,4))[0]
    mode=integer(0xc6dfbc);flags=r.read(0x53d400,0x18)
    return dict(mode=mode,menu=integer(0xc69d10),cursor=integer(0xc53488),
        stage=integer(0x53cad4),difficulty=integer(0x53d410),
        character=r.read(0x53cad0,1)[0],shot=r.read(0x53cad1,1)[0],
        frame=integer(0x436ef4),paused=bool(flags[0]),continuing=bool(flags[1]),
        cleared=bool(flags[3]),practice=bool(flags[4]),
        replay=bool(r.read(0x53d3dc,1)[0] or flags[5]),challenge=flags[0x14],
        result_phase=result_phase(r) if mode==7 else None)

