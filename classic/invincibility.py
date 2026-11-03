"""Version-locked, reversible in-memory collision bypass for th06nc."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
from editions import EDITIONS

EXPECTED_SHA = '48630a42a2eb6762d0db2a7e0d151203efbe67220fef7d2f9d0d51857928ac82'
# Ordinary hit: don't branch into hit handler; fall through to return 0.
# Laser hit: branch to existing non-hit/graze path; same branch-end address.
PATCHES = [(0x6c1ac, bytes.fromhex('7507'), bytes.fromhex('9090')),
           (0x6c3f4, bytes.fromhex('0f86df000000'), bytes.fromhex('90e9df000000'))]
ROOT = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
k = C.WinDLL('kernel32', use_last_error=True)
ps = C.WinDLL('psapi', use_last_error=True)
nt = C.WinDLL('ntdll')
u = C.WinDLL('user32')
k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k.OpenProcess.restype = W.HANDLE
k.CloseHandle.argtypes = [W.HANDLE]
k.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
k.WriteProcessMemory.argtypes = k.ReadProcessMemory.argtypes
k.VirtualProtectEx.argtypes = [W.HANDLE, C.c_void_p, C.c_size_t, W.DWORD, C.POINTER(W.DWORD)]
k.FlushInstructionCache.argtypes = [W.HANDLE, C.c_void_p, C.c_size_t]
k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
k.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
ps.EnumProcesses.argtypes = [C.POINTER(W.DWORD), W.DWORD, C.POINTER(W.DWORD)]
ps.EnumProcessModulesEx.argtypes = [W.HANDLE, C.POINTER(C.c_void_p), W.DWORD, C.POINTER(W.DWORD), W.DWORD]
nt.NtSuspendProcess.argtypes = nt.NtResumeProcess.argtypes = [W.HANDLE]
nt.NtSuspendProcess.restype = nt.NtResumeProcess.restype = W.LONG


def check(ok, label):
    if not ok:
        raise RuntimeError(f'{label}（Windows 错误 {C.get_last_error()}）')


def log(message):
    try:
        with (ROOT/'trainer.log').open('a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + message + '\n')
    except OSError:pass


def find_game(edition='classic'):
    ids = (W.DWORD * 4096)()
    n = W.DWORD()
    check(ps.EnumProcesses(ids, C.sizeof(ids), C.byref(n)), '无法枚举进程')
    found = []
    for pid in ids[:n.value//4]:
        handle = k.OpenProcess(0x1000, False, pid)
        if not handle:
            continue
        try:
            buf = C.create_unicode_buffer(32768)
            size = W.DWORD(len(buf))
            if k.QueryFullProcessImageNameW(handle, 0, buf, C.byref(size)):
                if Path(buf.value).name.lower() == EDITIONS[edition]['exe']:
                    found.append((pid, Path(buf.value)))
        finally:
            k.CloseHandle(handle)
    if len(found) != 1:
        raise RuntimeError(f"请先启动一个{EDITIONS[edition]['name']}游戏进程。" if not found else '检测到多个游戏，请只保留一个。')
    return found[0]


class Trainer:
    def __init__(self,edition='classic',patches=None):
        self.edition=edition;self.patches=EDITIONS[edition]['patches'] if patches is None else patches
        self.handle = None
        self.pid, self.path = find_game(edition)
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != EDITIONS[edition]['sha']:
            raise RuntimeError('游戏版本与已分析版本不一致，已拒绝修改。请重新适配。')
        self.handle = k.OpenProcess(0x438 | 0x800, False, self.pid)
        check(self.handle, '无法连接游戏，请确认游戏与本程序的权限一致')
        try:
            modules = (C.c_void_p * 1024)()
            n = W.DWORD()
            check(ps.EnumProcessModulesEx(self.handle, modules, C.sizeof(modules), C.byref(n), 3), '无法读取主模块')
            self.base = modules[0]
            self.status()
        except Exception:
            k.CloseHandle(self.handle)
            self.handle = None
            raise

    def alive(self):
        code = W.DWORD()
        return bool(self.handle and k.GetExitCodeProcess(self.handle, C.byref(code)) and code.value == 259)

    def read(self, rva, length):
        buf = C.create_string_buffer(length)
        size = C.c_size_t()
        check(k.ReadProcessMemory(self.handle, self.base+rva, buf, length, C.byref(size)), '读取失败')
        check(size.value == length, '读取长度不符')
        return buf.raw

    def status(self):
        states = []
        for rva, original, patched in self.patches:
            value = self.read(rva, len(original))
            if value not in (original, patched):
                raise RuntimeError(f'代码校验失败（{rva:X}），拒绝覆盖未知修改。')
            states.append(value == patched)
        return 'ON' if all(states) else 'OFF' if not any(states) else 'PARTIAL'

    def write(self, rva, data):
        old = W.DWORD()
        check(k.VirtualProtectEx(self.handle, self.base+rva, len(data), 0x40, C.byref(old)), '无法修改内存保护')
        try:
            size = C.c_size_t()
            buf = C.create_string_buffer(data)
            check(k.WriteProcessMemory(self.handle, self.base+rva, buf, len(data), C.byref(size)), '写入失败')
            check(size.value == len(data), '写入长度不符')
            check(k.FlushInstructionCache(self.handle, self.base+rva, len(data)), '刷新指令缓存失败')
        finally:
            ignored = W.DWORD()
            check(k.VirtualProtectEx(self.handle, self.base+rva, len(data), old.value, C.byref(ignored)), '恢复内存保护失败')

    def set_enabled(self, enabled):
        # Suspend briefly so no thread can execute partially replaced instructions.
        result = nt.NtSuspendProcess(self.handle)
        if result < 0:
            raise RuntimeError(f'无法短暂挂起进程：{result:#x}')
        before = []
        try:
            self.status()
            before = [(r, self.read(r, len(o))) for r,o,p in self.patches]
            for r,o,p in self.patches:
                self.write(r, p if enabled else o)
            if self.status() != ('ON' if enabled else 'OFF'):
                raise RuntimeError('写入后验证失败')
        except Exception:
            for r,data in before:
                self.write(r, data)
            raise
        finally:
            if nt.NtResumeProcess(self.handle) < 0:
                # Retry once; never silently leave the game suspended.
                if nt.NtResumeProcess(self.handle) < 0:
                    raise RuntimeError('恢复游戏运行失败，请重启游戏。')
        log(f'PID {self.pid}: ' + ('ON' if enabled else 'OFF'))

    def probe(self):
        pos,state=(0xbbfc38,0xbbfda8) if self.edition=='classic' else (0x551720,0x551888)
        return {'pid': self.pid, 'status': self.status(),
                'player_xyz': struct.unpack('<3f', self.read(pos, 12)),
                'player_state': self.read(state, 1)[0]}

    def close(self):
        if self.handle:
            if self.alive() and self.status() != 'OFF':
                self.set_enabled(False)
            k.CloseHandle(self.handle)
            self.handle = None

