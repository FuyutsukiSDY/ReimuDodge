"""One-file selector. Original backends run in separate processes and folders."""
import ctypes as C
from ctypes import wintypes as W
import hashlib,json,os,subprocess,sys,tempfile,traceback,shutil,time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
ASSETS=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
APP_ROOT=Path(sys.executable if getattr(sys,'frozen',False) else __file__).resolve().parent
MANIFEST=json.loads((ASSETS/'manifest.json').read_text(encoding='utf8'))
EDITIONS={'classic':('原典','2.0','classic'), 'new':('新典','3.0','new')}
BG='#F2F2F7';FG='#1C1C1E';MUTED='#6E6E73'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def prepare(edition,home):
    if edition not in EDITIONS:raise ValueError('未知版本')
    name,version,folder=EDITIONS[edition]
    source=ASSETS/'payloads'/f'{edition}.exe'
    expected=MANIFEST[edition]['sha256']
    if digest(source)!=expected:raise RuntimeError('内置版本校验失败，请重新取得完整程序')
    target_dir=home/folder
    target_dir.mkdir(parents=True,exist_ok=True)
    target=target_dir/'自动档灵梦.exe'
    if target.exists() and digest(target)==expected:return target
    fd,temporary=tempfile.mkstemp(prefix='backend-',suffix='.tmp',dir=target_dir)
    try:
        with os.fdopen(fd,'wb') as out,source.open('rb') as inp:
            for b in iter(lambda:inp.read(1024*1024),b''):out.write(b)
            out.flush();os.fsync(out.fileno())
        if digest(Path(temporary))!=expected:raise RuntimeError('写入版本文件校验失败')
        os.replace(temporary,target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target

class Selector:
    def __init__(self,root):
        self.root=root;self.child=None;self.selected=None;self.runtime=None
        root.title('自动档灵梦 Ver3.0 整合原典 by B站冬月爱吃沙丁鱼')
        root.iconbitmap(str(ASSETS/'reimu.ico'));root.configure(bg=BG)
        root.geometry('600x450');root.resizable(False,False)
        root.protocol('WM_DELETE_WINDOW',self.close)
        tk.Label(root,text='自动档灵梦',font=('Microsoft YaHei UI',27,'bold'),bg=BG,fg=FG).pack(anchor='w',padx=30,pady=(26,5))
        tk.Label(root,text='选择这次使用的游戏版本',font=('Microsoft YaHei UI',12),bg=BG,fg=MUTED).pack(anchor='w',padx=32,pady=(0,20))
        self.buttons=[]
        for key,color,description in [('classic','#007AFF','原典Ver2.0'),('new','#D74666','新典Ver3.0')]:
            name,version,_=EDITIONS[key]
            frame=tk.Frame(root,bg='white');frame.pack(fill='x',padx=30,pady=6)
            text=tk.Frame(frame,bg='white');text.pack(side='left',fill='x',expand=True,padx=18,pady=17)
            tk.Label(text,text=name,font=('Microsoft YaHei UI',17,'bold'),bg='white',fg=FG).pack(anchor='w')
            tk.Label(text,text=description,font=('Microsoft YaHei UI',10),bg='white',fg=MUTED).pack(anchor='w',pady=(5,0))
            button=tk.Button(frame,text='打开',font=('Microsoft YaHei UI',11),bg=color,fg='white',activebackground=color,activeforeground='white',relief='flat',bd=0,padx=20,pady=8,command=lambda e=key:self.launch(e))
            button.pack(side='right',padx=18);self.buttons.append(button)
        self.status=tk.StringVar(value='请选择版本')
        tk.Label(root,textvariable=self.status,wraplength=560,justify='left',font=('Microsoft YaHei UI',10),bg=BG,fg=MUTED).pack(anchor='w',padx=32,pady=(18,6))
        tk.Label(root,text='Ver3.0 by B站冬月爱吃沙丁鱼',font=('Microsoft YaHei UI',9),bg=BG,fg=MUTED).pack(side='bottom',anchor='e',padx=30,pady=14)
    def launch(self,edition):
        if self.child is not None:return
        for b in self.buttons:b.configure(state='disabled')
        self.status.set('正在准备 '+EDITIONS[edition][0]+'…');self.root.update_idletasks()
        try:
            if self.runtime is None:self.runtime=Path(tempfile.mkdtemp(prefix='Reimu-Ver3.0-'))
            exe=prepare(edition,self.runtime)
            # PyInstaller one-file children must own their extraction lifetime.
            env=os.environ.copy();env['PYINSTALLER_RESET_ENVIRONMENT']='1'
            unpack=self.runtime/'unpack';unpack.mkdir(exist_ok=True)
            env['TEMP']=env['TMP']=str(unpack)
            self.child=subprocess.Popen([str(exe)],cwd=exe.parent,env=env)
            self.selected=edition;self.root.withdraw();self.root.after(300,self.poll)
        except Exception as e:
            self.child=None
            self.clean_runtime()
            for b in self.buttons:b.configure(state='normal')
            self.status.set('启动失败，可重试')
            messagebox.showerror('无法启动',str(e),parent=self.root)
    def poll(self):
        if self.child is None:return
        code=self.child.poll()
        if code is None:self.root.after(300,self.poll);return
        name=EDITIONS[self.selected][0];self.child=None
        for b in self.buttons:b.configure(state='normal')
        self.clean_runtime()
        self.status.set('请选择版本')
        self.root.deiconify();self.root.lift()
    def close(self):
        # Never terminate a running backend while it may own keys or patches.
        if self.child is not None and self.child.poll() is None:
            self.root.withdraw();return
        if not self.clean_runtime():return
        self.root.destroy()
    def clean_runtime(self):
        if self.runtime is None:return True
        # Only delete the exact directory created by this process under TEMP.
        path=self.runtime
        expected=Path(tempfile.gettempdir()).resolve()
        if path.is_symlink() or path.resolve().parent!=expected or not path.name.startswith('Reimu-Ver3.0-'):
            raise RuntimeError('临时目录校验失败，已停止清理')
        for attempt in range(6):
            try:
                if path.exists():shutil.rmtree(path)
                self.runtime=None;return True
            except OSError:
                time.sleep(.1)
        messagebox.showerror('临时文件仍被占用','请关闭占用临时文件的程序后，再关闭此窗口以重试清理。',parent=self.root)
        return False

def acquire_instance():
    k=C.WinDLL('kernel32',use_last_error=True)
    k.CreateMutexW.argtypes=[W.LPVOID,W.BOOL,W.LPCWSTR];k.CreateMutexW.restype=W.HANDLE
    k.CloseHandle.argtypes=[W.HANDLE];k.CloseHandle.restype=W.BOOL
    h=k.CreateMutexW(None,False,'Local\\ReimuDualLocalSelector')
    if not h:raise C.WinError(C.get_last_error())
    if C.get_last_error()==183:k.CloseHandle(h);return None
    return h

def self_test():
    result={}
    with tempfile.TemporaryDirectory(prefix='reimu-dual-check-') as d:
        for edition in EDITIONS:
            target=prepare(edition,Path(d));log=target.parent/'session.jsonl';log.write_text('preserve-test',encoding='utf8')
            stamp=target.stat().st_mtime_ns;again=prepare(edition,Path(d))
            assert again==target and target.stat().st_mtime_ns==stamp and log.read_text()=='preserve-test'
            env=os.environ.copy();env['PYINSTALLER_RESET_ENVIRONMENT']='1'
            subprocess.run([str(target),'--log-self-test'],cwd=target.parent,env=env,check=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
            health=json.loads((target.parent/'log-self-test-result.json').read_text(encoding='utf8'))
            assert health['flushed']==1 and not health['error'],health
            result[edition]={'version':MANIFEST[edition]['version'],'sha256':digest(target),'isolated_directory':target.parent.name,'replay_protection':True}
    return result

if __name__=='__main__':
    if '--self-test' in sys.argv:self_test()
    else:
        lock=None
        try:
            lock=acquire_instance()
            root=tk.Tk()
            if lock is None:
                root.withdraw();messagebox.showinfo('自动档灵梦','选择窗口或所选版本已经运行，请先关闭当前版本。');root.destroy()
            else:Selector(root);root.mainloop()
        except Exception:
            messagebox.showerror('启动失败',traceback.format_exc())
        finally:
            if lock:C.WinDLL('kernel32').CloseHandle(W.HANDLE(lock))
