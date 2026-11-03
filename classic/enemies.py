"""Enemy contact geometry, verified against build 25306795 at RVA 39338.

The game passes 2/3 of the enemy's dimensions to circle-vs-rectangle
collision. We enclose that rectangle in a circle for conservative avoidance.
Only active, on-screen, contact-enabled objects enter that collision call.
"""
import numpy as np

POOL_RVA = 0xaee0b8
STRIDE = 0x10b0
COUNT = 256


def decode_enemies(raw):
    flags = np.ndarray((COUNT, 3), 'u1', raw, 0xbc, (STRIDE, 1))
    enabled = ((flags[:, 0] & 128) != 0) & ((flags[:, 1] & 7) == 7) & ((flags[:, 2] & 8) == 0)
    slots = np.flatnonzero(enabled)
    pos = np.ndarray((COUNT, 2), '<f4', raw, 0xb0, (STRIDE, 4))[enabled].astype(float)
    dims = np.ndarray((COUNT, 2), '<f4', raw, 0x2c0, (STRIDE, 4))[enabled].astype(float)
    vel = np.ndarray((COUNT, 2), '<f4', raw, 0x1084, (STRIDE, 4))[enabled].astype(float)
    vel[(flags[enabled, 0] & 64) != 0, 0] *= -1
    if not (np.isfinite(pos).all() and np.isfinite(dims).all() and np.isfinite(vel).all()
            and (abs(pos) < 10000).all() and (abs(vel) < 1000).all()
            and (dims >= 0).all() and (dims < 2048).all()):
        raise RuntimeError('敌机本体数据异常，已停止控制')
    # Use the actual single-precision scale from the game's collision caller.
    half = dims * float(np.float32(2 / 3)) * .5
    return slots, np.column_stack((pos, vel, half))


def enemy_hazards(enemies):
    """x,y,vx,vy,hx,hy -> conservative moving contact circles."""
    e = np.asarray(enemies, float).reshape(-1, 6)
    return np.column_stack((e[:, :4], np.linalg.norm(e[:, 4:6], axis=1)))


class EnemyTracker:
    def __init__(self,decoder=decode_enemies):
        self.decoder=decoder
        self.previous = {}
        self.frame = None

    def update(self, raw, frame):
        slots, enemies = self.decoder(raw)
        dt = frame - self.frame if self.frame is not None else 0
        # Do not replace velocities on duplicate paused frames. Scripted motion
        # is estimated only over short intervals; teleports start at the new
        # position rather than being extrapolated across the entire screen.
        if dt == 0 and self.frame is not None:
            for slot, e in zip(slots, enemies):
                old = self.previous.get(int(slot))
                if old is not None and np.array_equal(old[:2], e[:2]):
                    e[2:4] = old[2:4]
            return enemies
        for slot, e in zip(slots, enemies):
            old = self.previous.get(int(slot))
            if old is not None and 0 < dt <= 12:
                observed = (e[:2] - old[:2]) / dt
                if np.linalg.norm(observed) <= 16:
                    e[2:4] = observed
        self.previous = {int(slot): e.copy() for slot, e in zip(slots, enemies)}
        self.frame = frame
        return enemies
