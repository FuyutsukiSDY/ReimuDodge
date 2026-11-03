"""iOS Settings-inspired local Tk controls; no extra runtime dependency."""
import tkinter as tk
BG='#F2F2F7';TEXT='#1C1C1E';MUTED='#6E6E73';BLUE='#007AFF'

class Switch(tk.Canvas):
    def __init__(self,parent,variable,command=None):
        super().__init__(parent,width=54,height=32,bg='white',highlightthickness=0,takefocus=1,cursor='hand2')
        self.variable=variable;self.command=command
        self.bind('<Button-1>',self.toggle);self.bind('<space>',self.toggle);self.bind('<Return>',self.toggle)
        self.bind('<FocusIn>',lambda e:self.paint());self.bind('<FocusOut>',lambda e:self.paint())
        self.token=variable.trace_add('write',lambda *a:self.paint())
        self.bind('<Destroy>',self.cleanup);self.paint()
    def cleanup(self,event):
        if event.widget is self:
            try:self.variable.trace_remove('write',self.token)
            except tk.TclError:pass
    def toggle(self,event=None):
        old=bool(self.variable.get());self.variable.set(not old)
        try:
            if self.command and self.command(not old) is False:self.variable.set(old)
        except Exception:
            self.variable.set(old);raise
        return 'break'
    def paint(self):
        self.delete('all');on=bool(self.variable.get());color='#34C759' if on else '#D1D1D6'
        self.create_oval(1,2,29,30,fill=color,outline=color)
        self.create_rectangle(15,2,39,30,fill=color,outline=color)
        self.create_oval(25,2,53,30,fill=color,outline=color)
        x=27 if on else 3
        self.create_oval(x,4,x+24,28,fill='white',outline='#FFFFFF')
        if self.focus_get() is self:self.create_rectangle(0,0,53,31,outline=BLUE,dash=(2,2))

class Card(tk.Canvas):
    def __init__(self,parent):
        super().__init__(parent,bg=BG,highlightthickness=0,height=10)
        self.body=tk.Frame(self,bg='white');self.window=self.create_window(12,10,anchor='nw',window=self.body)
        self.bind('<Configure>',self.resize);self.body.bind('<Configure>',self.fit)
        # The body starts below the initial canvas viewport; seed its height
        # after child geometry settles instead of waiting for an unmapped body.
        self.after_idle(self.fit)
    def fit(self,event=None):self.configure(height=self.body.winfo_reqheight()+20)
    def resize(self,event):
        w=event.width;h=self.winfo_height();r=16
        self.delete('shell')
        self.create_polygon(r,0,w-r,0,w,0,w,r,w,h-r,w,h,w-r,h,r,h,0,h,0,h-r,0,r,0,0,smooth=True,splinesteps=20,fill='white',outline='white',tags='shell')
        self.tag_lower('shell');self.itemconfigure(self.window,width=max(10,w-24))

def label(parent,text,**kw):
    return tk.Label(parent,text=text,bg=kw.pop('bg','white'),fg=kw.pop('fg',TEXT),font=kw.pop('font',('Microsoft YaHei UI',10)),**kw)

def section(parent,title):
    label(parent,title,bg=BG,fg=MUTED,font=('Microsoft YaHei UI',10),anchor='w').pack(fill='x',padx=16,pady=(16,6))
    card=Card(parent);card.pack(fill='x');return card.body

def row(parent,title,detail,variable,color,symbol,command=None,separator=True,mode_variable=None):
    frame=tk.Frame(parent,bg='white');frame.pack(fill='x',padx=6,pady=10)
    label(frame,symbol,bg=color,fg='white',font=('Microsoft YaHei UI',12,'bold'),width=2,pady=4).pack(side='left',padx=(0,12))
    switch=Switch(frame,variable,command);switch.pack(side='right',padx=(10,0))
    copy=tk.Frame(frame,bg='white');copy.pack(side='left',fill='x',expand=True)
    label(copy,title,font=('Microsoft YaHei UI',11),anchor='w').pack(fill='x')
    label(copy,detail,fg=MUTED,font=('Microsoft YaHei UI',9),anchor='w').pack(fill='x',pady=(3,0))
    if mode_variable is not None:
        option=tk.Checkbutton(copy,text='仅决死（中弹后尝试）',variable=mode_variable,bg='white',activebackground='white',fg=MUTED,font=('Microsoft YaHei UI',9),anchor='w',bd=0,highlightthickness=0)
        option.pack(fill='x',pady=(3,0))
        def sync_mode(*args):option.configure(state='normal' if variable.get() else 'disabled')
        token=variable.trace_add('write',sync_mode)
        option.bind('<Destroy>',lambda e:variable.trace_remove('write',token) if e.widget is option else None)
        sync_mode()
    if separator:tk.Frame(parent,height=1,bg='#EEEEF0').pack(fill='x',padx=(48,0))
    return switch

def button(parent,title,command,primary=False):
    return tk.Button(parent,text=title,command=command,bg=BLUE if primary else '#F2F2F7',fg='white' if primary else BLUE,
        activebackground='#0065D1' if primary else '#E5E5EA',activeforeground='white' if primary else BLUE,
        relief='flat',bd=0,font=('Microsoft YaHei UI',10),padx=16,pady=9,cursor='hand2')

def build(app,root,credit):
    root.configure(bg=BG);root.geometry('960x820');root.minsize(940,720)
    footer=tk.Frame(root,bg=BG);footer.pack(side='bottom',fill='x',padx=24,pady=(4,12))
    label(footer,credit,bg=BG,fg=MUTED,font=('Microsoft YaHei UI',9),anchor='e').pack(side='right')
    header=tk.Frame(root,bg=BG);header.pack(fill='x',padx=28,pady=(24,4))
    label(header,'自动档灵梦 · 原典',bg=BG,font=('Microsoft YaHei UI',25,'bold')).pack(anchor='w')
    columns=tk.Frame(root,bg=BG);columns.pack(fill='both',expand=True,padx=24,pady=(6,0))
    right=tk.Frame(columns,bg=BG,width=416);right.pack(side='right',fill='y',padx=(20,0));right.pack_propagate(False)
    left_host=tk.Frame(columns,bg=BG);left_host.pack(side='left',fill='both',expand=True)
    scroll=tk.Canvas(left_host,bg=BG,highlightthickness=0,width=440)
    bar=tk.Scrollbar(left_host,orient='vertical',command=scroll.yview)
    bar.pack(side='right',fill='y');scroll.pack(side='left',fill='both',expand=True)
    scroll.configure(yscrollcommand=bar.set)
    left=tk.Frame(scroll,bg=BG);window=scroll.create_window(0,0,anchor='nw',window=left)
    left.bind('<Configure>',lambda e:scroll.configure(scrollregion=scroll.bbox('all')))
    scroll.bind('<Configure>',lambda e:scroll.itemconfigure(window,width=e.width))
    def wheel(event):
        widget=event.widget
        while widget is not None:
            if widget is left_host:
                scroll.yview_scroll(-int(event.delta/120),'units');return 'break'
            widget=getattr(widget,'master',None)
    root.bind('<MouseWheel>',wheel,add='+')
    settings=section(left,'自动避弹')
    label(settings,'自动操作 · 不修改游戏数据',fg=MUTED,anchor='w').pack(fill='x',padx=6,pady=(4,0))
    row(settings,'自动射击','持续射击 · Z',app.shoot,'#007AFF','射')
    row(settings,'安全追击敌机','安全范围内适当横向追击',app.safe_pursuit,'#5856D6','追')
    row(settings,'自动捡P点(安全范围)','优先大 P · 满火力后停止拾取',app.auto_pickup,'#FF3B30','P')
    label(settings,'',textvariable=app.power_status,fg=MUTED,anchor='w').pack(fill='x',padx=6,pady=5)
    row(settings,'自动 Bomb','关闭仅决死：预判危险 + 决死补救',app.auto_bomb,'#FF9500','弹',mode_variable=app.deathbomb_only)
    row(settings,'仅预览','显示路线，不发送操作按键',app.preview,'#5AC8FA','览')
    modifiers=section(left,'修改类')
    label(modifiers,'修改游戏数据 · 可单独开启或关闭',fg=MUTED,anchor='w').pack(fill='x',padx=6,pady=(4,0))
    row(modifiers,'无敌模式','开启 F6 · 关闭 F7',app.god_toggle,'#AF52DE','免',app.change_invincibility)
    row(modifiers,'无限残机','中弹仍计数 · 关闭后正常消耗',app.infinite_lives,'#FF2D55','命',lambda on:app.change_resource('lives',on))
    row(modifiers,'无限 Bomb','释放后补充 · 不改变释放时机',app.infinite_bombs,'#FF9500','∞',lambda on:app.change_resource('bombs',on),separator=False)
    control=section(left,'运行控制')
    label(control,'回到游戏后按 F8 开始 / 停止',font=('Microsoft YaHei UI',11,'bold'),anchor='w').pack(fill='x',padx=6,pady=(7,4))
    label(control,'F9 紧急停止 · Esc 或切出游戏也会停止',fg=MUTED,font=('Microsoft YaHei UI',9),anchor='w').pack(fill='x',padx=6)
    buttons=tk.Frame(control,bg='white');buttons.pack(fill='x',padx=6,pady=12)
    button(buttons,'连接 / 刷新',app.connect,True).pack(side='left',fill='x',expand=True,padx=(0,8))
    button(buttons,'停止控制',lambda:app.stop('已手动停止')).pack(side='left',fill='x',expand=True)
    label(control,'',textvariable=app.status,fg=MUTED,wraplength=400,justify='left',anchor='w',font=('Microsoft YaHei UI',9)).pack(fill='x',padx=6,pady=(0,8))
    label(control,'',textvariable=app.log_status,fg=MUTED,wraplength=390,justify='left').pack(fill='x',padx=6,pady=6)
    protection=section(left,'录像保护')
    label(protection,'Replay 保存状态',font=('Microsoft YaHei UI',11,'bold'),anchor='w').pack(fill='x',padx=6,pady=(5,6))
    label(protection,'',textvariable=app.replay_status,fg=MUTED,wraplength=400,justify='left',anchor='w',font=('Microsoft YaHei UI',9)).pack(fill='x',padx=6,pady=(0,8))
    preview=section(right,'实时预览')
    app.canvas=tk.Canvas(preview,width=384,height=448,bg='#101025',highlightthickness=0)
    app.canvas.pack(pady=6)
    label(preview,'敌弹 · 橙色敌机 · 蓝色激光 · 黄线避让 · 青点目标',fg=MUTED,font=('Microsoft YaHei UI',9)).pack(pady=(8,6))
    state=section(right,'当前状态')
    label(state,'',textvariable=app.god_status,fg=MUTED,wraplength=380,justify='left',anchor='w',font=('Microsoft YaHei UI',9)).pack(fill='x',padx=6,pady=8)
    label(state,'F9 只停止按键控制。\n无敌与无限资源需单独关闭；退出时恢复。\n录像能否保存请查看左侧状态。',fg=MUTED,justify='left',anchor='w',font=('Microsoft YaHei UI',9)).pack(fill='x',padx=6,pady=(0,8))
