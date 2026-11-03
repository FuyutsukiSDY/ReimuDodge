"""Build-locked replay-save inhibition for the lifetime of the game process.

The recording finalizer at 6DB10 normally serializes a replay then follows
the keep-recording/cleanup branch at 6E04F. Jump there BEFORE serialization.
Unlike returning from the function, this retains its recording cleanup.
The playback branch at 6DB49 remains untouched. No replay files are deleted.
Closing this handle intentionally does not restore the patch: otherwise
closing the helper would allow saving assisted input. Restart the game to reset.
"""
from invincibility import Trainer, k, nt, log

RVA = 0x6db4f
ORIGINAL = bytes.fromhex('4885d20f84')
BLOCKED = bytes.fromhex('e9fb040000')  # jmp 6E04F; bypass serialization/enqueue.


class ReplayGuard(Trainer):
    def status(self):
        value = self.read(RVA, len(ORIGINAL))
        if value not in (ORIGINAL, BLOCKED):
            raise RuntimeError('录像保存代码不匹配，拒绝启动辅助')
        return value == BLOCKED

    def ensure(self):
        if not self.alive():
            raise RuntimeError('游戏已退出，录像保护未生效')
        if self.status():
            return
        result = nt.NtSuspendProcess(self.handle)
        if result < 0:
            raise RuntimeError('无法启用录像保护，辅助未启动')
        attempted = False
        try:
            if not self.status():
                attempted = True
                self.write(RVA, BLOCKED)
            if not self.status():
                raise RuntimeError('录像保护校验失败，辅助未启动')
        except Exception:
            # No input or invincibility has been enabled by this activation yet.
            if attempted:
                self.write(RVA, ORIGINAL)
            raise
        finally:
            if nt.NtResumeProcess(self.handle) < 0 and nt.NtResumeProcess(self.handle) < 0:
                raise RuntimeError('恢复游戏运行失败，请重启游戏')
        log(f'PID {self.pid}: replay saving blocked until game restart')

    def set_enabled(self, enabled):
        raise RuntimeError('录像保护不能手动解除；请重启游戏')

    def close(self):
        if self.handle:
            k.CloseHandle(self.handle)
            self.handle = None
