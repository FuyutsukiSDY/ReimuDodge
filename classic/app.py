import ctypes as C
from ctypes import wintypes as W
import json
import traceback
import faulthandler
import math
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import messagebox
from ui import build as build_ui
from engine import plan, ACTIONS
from routes import guidance, LateralStream
from search_budget import search_width
from session_log import SessionLog
from reader import Reader, SnapshotNotReady
from autobomb import BombGuard
from pursuit import Pursuit
import extra_policy
from power_collect import read_power_items,choose as collect_power
from shooting import Shooting
from invincibility import Trainer
from resources import ResourceTrainer
from replay_guard import ReplayGuard, RVA as REPLAY_RVA, BLOCKED as REPLAY_BLOCKED

VERSION='2.0'
REPLAY_PROTECTION=True  # Private local build; release builder forces True.
CREDIT='原典Ver2.0 by B站冬月爱吃沙丁鱼'

ROOT=Path(sys.executable if getattr(sys,'frozen',False) else __file__).resolve().parent
u=C.WinDLL('user32',use_last_error=True)
u.GetForegroundWindow.restype=W.HWND
u.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]

class Mouse(C.Structure):
    _fields_=[('dx',W.LONG),('dy',W.LONG),('data',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]
class Key(C.Structure):
    _fields_=[('vk',W.WORD),('scan',W.WORD),('flags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]
class Payload(C.Union):
    _fields_=[('ki',Key),('mi',Mouse)]
class Input(C.Structure):
    _fields_=[('type',W.DWORD),('payload',Payload)]
u.SendInput.argtypes=[W.UINT,C.POINTER(Input),C.c_int]

class Keyboard:
    def __init__(self):self.held=set()
    def set(self,wanted):
        scans={'left':0x4b,'right':0x4d,'up':0x48,'down':0x50,'shift':0x2a,'z':0x2c,'x':0x2d,'esc':0x01}
        # Release before pressing opposite directions.
        for key in sorted(self.held-wanted)+sorted(wanted-self.held):
            flag=8|(1 if key in ('left','right','up','down') else 0)|(2 if key not in wanted else 0)
            event=Input(type=1,payload=Payload(ki=Key(0,scans[key],flag,0,0)))
            if u.SendInput(1,C.byref(event),C.sizeof(Input))!=1:
                raise RuntimeError('Windows 未接受按键，请检查游戏与程序权限')
            if key in wanted:self.held.add(key)
            else:self.held.discard(key)

def game_focused(pid):
    value=W.DWORD();u.GetWindowThreadProcessId(u.GetForegroundWindow(),C.byref(value))
    return value.value==pid

class App:
    def __init__(self,root):
        self.root=root;self.reader=None;self.keys=Keyboard();self.armed=False;self.bomb_guard=BombGuard();self.shooting=Shooting();self.invincibility=None;self.replay_guard=None
        self.last_frame=None;self.last_change=time.perf_counter();self.previous=0
        self.lateral_stream=LateralStream()
        self.resource_trainers={}
        self.pursuit=Pursuit()
        self.session_log=SessionLog(ROOT/'session.jsonl')
        self.last_log_time=-1;self.last_log_health=0
        self.log_status=tk.StringVar(value='详细记录：等待开始控制')
        self.prev_keys={key:bool(u.GetAsyncKeyState(key)&0x8000) for key in (0x75,0x76,0x77,0x78,0x1b)};self.tick_start=time.perf_counter()
        self.invalid_since=None;self.awaiting_respawn=False
        self.last_draw=0;self.last_snapshot=None;self.last_path=None;self.cycles=0;self.max_ms=0;self.waiting=False
        root.title(f'自动档灵梦 · {CREDIT}')
        root.iconbitmap(str(Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'reimu.ico'))
        self.status=tk.StringVar(value='未启动控制。连接预览后，回游戏按 F8。')
        self.edition='classic'
        self.classic_mode=tk.BooleanVar(value=True)
        self.edition_label=tk.StringVar(value='原典 · N12 退路优化测试 · 普通窗口版')
        self.shoot=tk.BooleanVar(value=False)
        self.safe_pursuit=tk.BooleanVar(value=True)
        self.auto_pickup=tk.BooleanVar(value=True)
        self.power_status=tk.StringVar(value="火力：等待连接")
        self.auto_bomb=tk.BooleanVar(value=True)
        self.deathbomb_only=tk.BooleanVar(value=True)
        self.preview=tk.BooleanVar(value=False)
        self.god_toggle=tk.BooleanVar(value=False)
        self.infinite_lives=tk.BooleanVar(value=False)
        self.infinite_bombs=tk.BooleanVar(value=False)
        self.god_status=tk.StringVar(value='无敌：尚未读取，不自动开启')
        self.replay_status=tk.StringVar(value='使用辅助后禁存录像；关闭辅助仍保持，重启游戏恢复。' if REPLAY_PROTECTION else '本地测试版：允许保存 Replay；已被禁存的游戏需重启。')
        self.god_checked=0
        build_ui(self,root,CREDIT)
        root.protocol('WM_DELETE_WINDOW',lambda:self.close('窗口关闭'))
        root.report_callback_exception=self.callback_error
        self.event('app_open',version=VERSION,replay_protection=REPLAY_PROTECTION)
        root.after(50,self.tick)

    def start_control(self,now,automatic=False):
        if not self.preview.get():self.protect_replay()
        self.armed=True;self.previous=0;self.last_change=now
        self.waiting=False;self.invalid_since=None;self.awaiting_respawn=False
        self.lateral_stream.reset();self.pursuit.reset();self.bomb_guard=BombGuard()
        self.last_frame=self.read_snapshot()['frame']
        self.event('started',edition=self.edition,frame=self.last_frame,automatic=automatic,
                   auto_bomb=self.auto_bomb.get(),deathbomb_only=self.deathbomb_only.get(),
                   auto_shoot=self.shoot.get(),preview=self.preview.get())

    def connect(self):
        self.stop('正在连接，只读取数据')
        try:
            if self.reader:self.reader.close();self.reader=None
            self.reader=Reader(self.edition);s=self.read_snapshot();self.last_snapshot=s
            self.last_frame=s['frame'];self.draw(s,None)
            self.status.set(f"已连接：{len(s['bullets'])} 个敌弹，{len(s['enemies'])} 个有接触判定的敌机，{len(s['lasers'])} 条激光。回游戏按 F8 启动。")
        except Exception as e:self.status.set(str(e))

    def read_snapshot(self):
        s=self.reader.snapshot()
        try:
            s['power'],s['power_items']=read_power_items(self.reader)
            self.power_status.set(f"火力：{s['power']}/128"+(' · MAX，停止追捡' if s['power']==128 else ' · 安全大 P 优先'))
        except Exception as e:
            s['power']=None;s['power_items']=[];s['pickup_error']=str(e)
            self.power_status.set('火力读取异常，停止主动拾取')
        s['route']=guidance(s['player'],s['bullets'],s['lasers'],s['enemies'],s.get('bounds',(8,16,376,432)))
        s['extra_new_strategy']=extra_policy.enabled(s,True)
        if s['extra_new_strategy']:s['route']=extra_policy.guidance(s)
        if self.invalid_since is not None:
            self.event('snapshot_recovered',frame=s['frame'])
            self.invalid_since=None
        return s

    def retry_snapshot(self,error,now):
        if not self.armed:
            self.stop(str(error)+'，请稍后重试连接')
            return
        if self.invalid_since is None:
            self.invalid_since=now
            self.event('snapshot_retry',details=error.details)
        if now-self.invalid_since>=2.0:
            self.stop('敌弹数据持续异常超过 2 秒，已停止；请保留日志')
            self.event('snapshot_retry_failed',details=error.details)
            return
        self.wait_for_fresh('敌弹数据暂时不完整，正在重读')
        self.last_frame=None;self.previous=0
        self.last_snapshot=None;self.last_path=None

    def protect_replay(self):
        if not REPLAY_PROTECTION:return
        if self.replay_guard and not self.replay_guard.alive():
            self.replay_guard.close();self.replay_guard=None
        if self.replay_guard is None:self.replay_guard=ReplayGuard()
        if self.reader and self.replay_guard.pid!=self.reader.pid:
            raise RuntimeError('游戏进程已更换，请重新连接')
        was_blocked=self.replay_guard.status()
        self.replay_guard.ensure()
        self.replay_status.set('Replay：本次游戏已禁存录像，关闭辅助仍保持；重启游戏恢复。')
        if not was_blocked:self.event('replay_blocked',pid=self.replay_guard.pid,scope='game_process')

    def change_invincibility(self,enabled):
        try:
            self.keys.set(set());self.bomb_guard.release();self.shooting.reset()
            if self.invincibility and not self.invincibility.alive():
                self.invincibility.close();self.invincibility=None
            if self.invincibility is None:self.invincibility=Trainer(self.edition)
            if enabled:self.protect_replay()
            self.invincibility.set_enabled(enabled)
            self.god_status.set('无敌：已开启（演练，自动 Bomb 不触发）' if enabled else '无敌：已关闭（正常判定）')
            if hasattr(self,'god_toggle'):self.god_toggle.set(enabled)
            self.event('invincibility_changed',enabled=enabled,pid=self.invincibility.pid)
            return True
        except Exception as e:
            self.stop('无敌开关失败：'+str(e))
            self.god_status.set('无敌：状态未确认，请检查游戏或重启游戏')
            return False

    def change_resource(self,kind,enabled):
        try:
            trainer=self.resource_trainers.get(kind)
            if trainer and not trainer.alive():
                trainer.close();self.resource_trainers.pop(kind);trainer=None
            if trainer is None:
                trainer=ResourceTrainer(self.edition,kind);self.resource_trainers[kind]=trainer
            if enabled:self.protect_replay()
            trainer.set_enabled(enabled)
            self.event('resource_changed',edition=self.edition,kind=kind,enabled=enabled,pid=trainer.pid)
            self.status.set(('无限残机' if kind=='lives' else '无限 Bomb')+('已开启；关闭开关恢复正常消耗。' if enabled else '已关闭。'))
            return True
        except Exception as e:
            self.stop('资源开关失败：'+str(e))
            return False

    def close_resources(self):
        errors=[]
        for kind,trainer in list(getattr(self,'resource_trainers',{}).items()):
            try:
                trainer.close();del self.resource_trainers[kind]
                (self.infinite_lives if kind=='lives' else self.infinite_bombs).set(False)
            except Exception as e:errors.append(str(e))
        if errors:raise RuntimeError('；'.join(errors))

    def event(self,event,**details):
        try:
            with (ROOT/'events.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps(dict(time=time.time(),event=event,**details),ensure_ascii=False)+'\n')
        except OSError:
            pass  # Diagnostic failure must not prevent releasing held keys.

    def callback_error(self,kind,value,tb):
        self.stop('程序回调异常，控制已停止；请查看 crash.log')
        try:
            with (ROOT/'crash.log').open('a',encoding='utf-8') as f:
                f.write(''.join(traceback.format_exception(kind,value,tb)))
        except OSError:pass

    def wait_for_fresh(self,reason):
        self.keys.set(set());self.bomb_guard.release();self.shooting.reset()
        if not self.waiting:self.event('waiting',reason=reason,frame=self.last_frame)
        self.waiting=True
        self.status.set(reason+'；已松键，等待新数据。F8 可取消控制。')

    def stop(self,message):
        self.pursuit.reset()
        self.lateral_stream.reset()
        self.event('stopped',reason=message,frame=self.last_frame,was_armed=self.armed)
        self.waiting=False
        self.invalid_since=None;self.awaiting_respawn=False
        self.armed=False
        self.bomb_guard.release()
        self.shooting.reset()
        try:self.keys.set(set())
        except Exception as e:message+=f'；松键失败：{e}，请手动按下并松开方向键/Shift/Z/X'
        self.status.set(message)

    def close(self,reason='窗口关闭'):
        self.stop('正在退出')
        try:
            self.close_resources()
            if self.invincibility:self.invincibility.close();self.invincibility=None
        except Exception as e:
            self.event('restore_failed',error=str(e))
            self.status.set('开关恢复失败：请重启游戏后再关闭窗口。'+str(e))
            return
        if hasattr(self,'session_log'):self.session_log.close()
        log=getattr(self,'session_log',None)
        if log:self.event('log_final',**log.health())
        self.event('app_exit',reason=reason,log_error=log.error if log else None,log_dropped=log.dropped if log else 0,log_pending=log.queue.qsize() if log else 0)
        if self.reader:self.reader.close()
        if self.replay_guard:self.replay_guard.close();self.replay_guard=None
        self.root.destroy()

    def draw(self,s,path):
        c=self.canvas;c.delete('all')
        c.create_rectangle(*s.get('bounds',(8,16,376,432)),outline='#444460')
        for x,y,vx,vy,r in s['bullets']:
            if -30<x<414 and -30<y<478:
                c.create_oval(x-r,y-r,x+r,y+r,outline='#ff9d9d')
        for ex,ey,vx,vy,hx,hy in s['enemies']:
            c.create_rectangle(ex-hx,ey-hy,ex+hx,ey+hy,outline='#ff9b30',width=2)
        for l in s['lasers']:
            x,y=l['origin'];dx,dy=math.cos(l['angle']),math.sin(l['angle'])
            c.create_line(x+dx*l['start'],y+dy*l['start'],x+dx*l['end'],y+dy*l['end'],fill='#52baff',width=max(2,l['width']))
        x,y=s['player'];c.create_oval(x-3,y-3,x+3,y+3,fill='white')
        if s.get('route'):
            gx,gy=s['route']['target'];c.create_oval(gx-4,gy-4,gx+4,gy+4,outline='#45e5d0',width=2)
        if path is not None:
            coords=[x,y]+[float(v) for v in path.ravel()]
            c.create_line(*coords,fill='#ffee60',width=2)

    def tick(self):
        started=time.perf_counter()
        try:
            for key in self.prev_keys:
                down=bool(u.GetAsyncKeyState(key)&0x8000);edge=down and not self.prev_keys[key];self.prev_keys[key]=down
                if not edge:continue
                if key in (0x75,0x76):self.change_invincibility(key==0x75)
                if key==0x78:self.stop('F9 紧急停止（程序保持打开）')
                if key==0x1b:self.stop('检测到 Esc，已停止。解除暂停后按 F8 重启。')
                if key==0x77:
                    if self.armed:self.stop('已停止控制')
                    else:
                        if not self.reader:self.reader=Reader(self.edition)
                        if not game_focused(self.reader.pid):
                            self.status.set('请切回游戏，再按 F8');continue
                        self.start_control(started)
            if self.armed:
                if not game_focused(self.reader.pid):self.stop('已切出游戏，控制停止')
                elif started-self.tick_start>.20:
                    self.wait_for_fresh('检测到短时卡顿')
                    self.last_frame=self.read_snapshot()['frame'];self.last_change=started
                else:
                    s=self.read_snapshot();frame=s['frame'];snapshot_ms=(time.perf_counter()-started)*1000
                    if self.last_frame is not None and frame<self.last_frame:
                        self.wait_for_fresh('切关或场景重新开始，等待新画面')
                        self.event('scene_reset',previous_frame=self.last_frame,new_frame=frame)
                        self.last_frame=frame;self.last_change=started
                        self.previous=0;self.bomb_guard=BombGuard()
                        self.lateral_stream.reset()
                        self.last_snapshot=s;self.last_path=None
                    elif frame==self.last_frame:
                        if started-self.last_change>.08:self.keys.set(set())
                        if started-self.last_change>1.5:self.wait_for_fresh('游戏计时暂未推进')
                    else:
                        jump=frame-self.last_frame if self.last_frame is not None else 1
                        self.last_frame=frame;self.last_change=started
                        if jump>12:
                            self.wait_for_fresh('跳过过期的动作，重新同步')
                            self.tick_start=started
                            self.root.after(16,self.tick)
                            return
                        if self.waiting and not (self.awaiting_respawn and s['state'] not in (0,3)):
                            self.event('resumed',frame=frame);self.waiting=False
                        if s['state'] in (0,3):self.awaiting_respawn=False
                        old_action=self.previous
                        s['route']=self.lateral_stream.update(frame,s['player'],s['bullets'],s['lasers'],s['enemies'],s['bounds'],s.get('route'),s['state'])
                        if s.get('stage')==3 and s.get('route') and s['route']['mode']=='stream':
                            s['route']=dict(s['route'],weight=s['route']['weight']*.5)
                        planning_started=time.perf_counter()
                        if s['state']==2:
                            # Deathbomb must be attempted before expensive planning.
                            a,path,cost=0,None,0
                        else:
                            if s.get('extra_new_strategy'):
                                a,path,cost=extra_policy.choose(s,old_action)
                            else:
                                a,path,cost=plan(s['player'],s['bullets'],s['lasers'],s['speeds'],s['radius'],old_action,enemies=s['enemies'],bounds=s.get('bounds',(8,16,376,432)),route_override=s['route'],width=search_width(s),corner_escape=False,safety_margin=0,reserve_space=s.get('stage')==5,laser_position=s.get('stage')==6,mixed_retreat=s.get('stage')==6,laser_options=s.get('stage')==6)
                            (a,path,cost),s['pickup']=collect_power(s,old_action,(a,path,cost),self.auto_pickup.get())
                            if s['pickup']['active']:
                                s['pursuit']={'active':False,'reason':'pickup_priority'}
                                self.pursuit.reset()
                            else:
                                (a,path,cost),s['pursuit']=self.pursuit.choose(s,old_action,(a,path,cost),self.safe_pursuit.get())
                        planning_ms=(time.perf_counter()-planning_started)*1000
                        reason=self.bomb_guard.reason(s,a,old_action,self.auto_bomb.get(),self.preview.get(),deathbomb_only=self.deathbomb_only.get())
                        holding=self.bomb_guard.holding(frame,started)
                        can_wait_for_rescue=(self.auto_bomb.get() and not self.preview.get() and not s['invincible'] and s['bombs']>0 and s['death_window']>0)
                        if (self.awaiting_respawn and s['state'] not in (0,3)) or (s['state']==2 and not (reason or holding or can_wait_for_rescue)):
                            if not self.awaiting_respawn:self.event('death_wait',frame=frame,bombs=s['bombs'],death_window=s['death_window'])
                            self.awaiting_respawn=True;self.previous=0
                            self.last_snapshot=s;self.last_path=None
                            self.wait_for_fresh('已中弹，等待复活后自动继续')
                        else:
                            self.previous=a;self.last_snapshot=s;self.last_path=path
                            x,y,focus=ACTIONS[a];wanted=set()
                            if x:wanted.add('left' if x<0 else 'right')
                            if y:wanted.add('up' if y<0 else 'down')
                            if focus:wanted.add('shift')
                            if self.shooting.wanted(frame,self.shoot.get()):wanted.add('z')
                            if (reason or holding) and self.auto_bomb.get():wanted.add('x')
                            if self.preview.get():wanted=set()
                            sent=False
                            if not game_focused(self.reader.pid):self.stop('已切出游戏，控制停止')
                            elif time.perf_counter()-started>(.05 if self.edition=='classic' else .10):self.wait_for_fresh('此次规划已过期')
                            else:
                                if wanted:self.protect_replay()
                                input_started=time.perf_counter();self.keys.set(wanted);sent=True
                                input_ms=(time.perf_counter()-input_started)*1000
                                if reason:self.bomb_guard.mark(frame,time.perf_counter(),emergency=s['state']==2)
                            mode='只预览' if self.preview.get() else '演练（无敌开启，自动 Bomb 不触发）' if s['invincible'] else '正常判定测试'
                            detail=reason if reason and sent else '未找到无碰撞预测路线' if cost>1e5 else '规划中'
                            if self.armed and not self.waiting:self.status.set(f"{mode} | 敌弹 {len(s['bullets'])} | 敌机 {len(s['enemies'])} | Bomb {s['bombs']} | {detail}")
                            self.cycles+=1
                            if self.last_log_time<0 or started-self.last_log_time>=.2 or cost>1e5 or reason or s['state']==2:
                                accepted=self.session_log.submit(dict(time=time.time(),power=s.get('power'),power_items=s.get('power_items'),pickup=s.get('pickup'),pickup_error=s.get('pickup_error'),auto_pickup=self.auto_pickup.get(),strategy='new_extra_experiment' if s.get('extra_new_strategy') else 'classic_n12',extra_new_strategy=s.get('extra_new_strategy',False),corner_escape=False,safety_margin=0,reserve_space=s.get('stage')==5,laser_position=s.get('stage')==6,mixed_retreat=s.get('stage')==6,laser_options=s.get('stage')==6,search_width=search_width(s),safe_pursuit=self.safe_pursuit.get(),pursuit=s.get('pursuit'),edition=self.edition,stage=s.get('stage'),resources={kind:getattr(self,name).get() for kind,name in (('lives','infinite_lives'),('bombs','infinite_bombs')) if hasattr(self,name)},frame=frame,player=s['player'],bullets=s['bullets'],bullet_half=s.get('bullet_half'),player_half=s.get('player_half'),lasers=s['lasers'],enemies=s['enemies'],action=a,previous_action=old_action,cost=cost,decision_ms=(time.perf_counter()-started)*1000,snapshot_ms=snapshot_ms,planning_ms=planning_ms,input_ms=input_ms if sent else None,log_dropped=self.session_log.dropped,route=s.get('route'),speeds=s['speeds'],radius=s['radius'],bounds=s['bounds'],input_sent=sent,auto_bomb=self.auto_bomb.get(),deathbomb_only=self.deathbomb_only.get(),auto_shoot=self.shoot.get(),invincible=s['invincible'],state=s['state'],bombs=s['bombs'],bomb_active=s['bomb_active'],death_window=s['death_window'],bomb_reason=reason,bomb_key_sent=bool(sent and 'x' in wanted)))
                                if accepted:self.last_log_time=started
            if started-self.god_checked>.5:
                self.god_checked=started
                for kind,trainer in list(getattr(self,'resource_trainers',{}).items()):
                    if not trainer.alive():
                        trainer.close();del self.resource_trainers[kind]
                        (self.infinite_lives if kind=='lives' else self.infinite_bombs).set(False)
                try:
                    if self.reader:
                        replay_blocked=self.reader.replay_blocked()
                        self.replay_status.set('Replay：本次游戏已禁存录像；重启游戏恢复。' if replay_blocked else ('Replay：尚未禁存；使用辅助后将禁存至游戏重启。' if REPLAY_PROTECTION else 'Replay：本地测试版允许保存辅助录像。'))
                        enabled=self.reader.invincible()
                        self.god_toggle.set(enabled)
                        self.god_status.set('无敌：已开启（演练，自动 Bomb 不触发）' if enabled else '无敌：已关闭（正常判定）')
                    elif self.invincibility and not self.invincibility.alive():self.god_status.set('无敌：游戏已退出，下次启动不会自动开启')
                except Exception:self.god_status.set('无敌：无法读取当前状态')
            if self.last_snapshot and started-self.last_draw>.12:
                self.draw(self.last_snapshot,self.last_path);self.last_draw=started
        except SnapshotNotReady as e:
            self.retry_snapshot(e,started)
        except Exception as e:
            self.stop(str(e))
            self.event('error',error=str(e),trace=traceback.format_exc())
        if started-self.last_log_health>=2:
            self.last_log_health=started
            health=self.session_log.health()
            issue=health['error'] or ('记录线程已停止' if not health['alive'] else '')
            if self.cycles>10 and not health['submitted']:issue='未收到详细数据'
            self.log_status.set('详细记录异常：'+str(issue) if issue else f"详细记录：已落盘 {health['flushed']} 条 · 丢弃 {health['dropped']}")
            self.event('log_health',cycles=self.cycles,armed=self.armed,**health)
        elapsed=time.perf_counter()-started;self.max_ms=max(self.max_ms,elapsed*1000)
        self.tick_start=started
        self.root.after(max(1,int((1/60-elapsed)*1000)),self.tick)

if __name__=='__main__':
    if '--log-self-test' in sys.argv:
        log=SessionLog(ROOT/'log-self-test.jsonl')
        log.submit(dict(test=True,version=VERSION))
        log.close()
        (ROOT/'log-self-test-result.json').write_text(json.dumps(log.health(),ensure_ascii=False),encoding='utf-8')
    elif '--check' in sys.argv:
        edition='classic'
        reader=Reader(edition)
        try:
            s=reader.snapshot();a,path,cost=plan(s['player'],s['bullets'],s['lasers'],s['speeds'],s['radius'],enemies=s['enemies'],bounds=s.get('bounds',(8,16,376,432)),route_override=guidance(s['player'],s['bullets'],s['lasers'],s['enemies'],s['bounds']),width=search_width(s),corner_escape=False,safety_margin=0,reserve_space=s.get('stage')==5,laser_position=s.get('stage')==6,mixed_retreat=s.get('stage')==6,laser_options=s.get('stage')==6)
            (ROOT/'diagnostic.json').write_text(json.dumps(dict(edition=edition,pid=reader.pid,bullets=len(s['bullets']),lasers=len(s['lasers']),enemies=len(s['enemies']),player=s['player'],action=a,cost=cost,input_size=C.sizeof(Input),read_only=True,bombs=s['bombs'],bomb_active=s['bomb_active'],death_window=s['death_window']),indent=2),encoding='utf-8')
        finally:reader.close()
    else:
        crash_file=(ROOT/'crash.log').open('a',encoding='utf-8')
        faulthandler.enable(file=crash_file,all_threads=True)
        root=tk.Tk();app=App(root)
        try:root.mainloop()
        except BaseException:
            app.stop('未处理异常，已停止控制')
            traceback.print_exc(file=crash_file)
        finally:
            app.keys.set(set())
            app.session_log.close()
            try:
                app.close_resources()
                if app.invincibility:app.invincibility.close()
                if app.replay_guard:app.replay_guard.close()
            except Exception:traceback.print_exc(file=crash_file)
            faulthandler.disable();crash_file.close()

