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
    root.configure(bg=BG);root.geometry('920x900');root.minsize(900,880)
    footer=tk.Frame(root,bg=BG);footer.pack(side='bottom',fill='x',padx=24,pady=(4,12))
    label(footer,credit,bg=BG,fg=MUTED,font=('Microsoft YaHei UI',9),anchor='e').pack(side='right')
    header=tk.Frame(root,bg=BG);header.pack(fill='x',padx=28,pady=(24,4))
    label(header,'自动档灵梦 · 新典',bg=BG,font=('Microsoft YaHei UI',25,'bold')).pack(anchor='w')
    columns=tk.Frame(root,bg=BG);columns.pack(fill='both',expand=True,padx=24,pady=(6,0))
    right=tk.Frame(columns,bg=BG,width=416);right.pack(side='right',fill='y',padx=(20,0));right.pack_propagate(False)
    left_host=tk.Frame(columns,bg=BG);left_host.pack(side='left',fill='both',expand=True)
    scroll=tk.Scrollbar(left_host,orient='vertical');scroll.pack(side='right',fill='y')
    viewport=tk.Canvas(left_host,bg=BG,highlightthickness=0,yscrollcommand=scroll.set)
    viewport.pack(side='left',fill='both',expand=True);scroll.configure(command=viewport.yview)
    left=tk.Frame(viewport,bg=BG);window=viewport.create_window(0,0,window=left,anchor='nw')
    left.bind('<Configure>',lambda e:viewport.configure(scrollregion=viewport.bbox('all')))
    viewport.bind('<Configure>',lambda e:viewport.itemconfigure(window,width=e.width))
    def wheel(event):
        if str(event.widget).startswith(str(left_host)):viewport.yview_scroll(-int(event.delta/120),'units')
    root.bind('<MouseWheel>',wheel,add='+')
    settings=section(left,'自动避弹')
    row(settings,'自动射击','持续射击 · Z',app.shoot,'#007AFF','射')
    row(settings,'安全追击敌机','安全上穿后横移 · 保留完整追击路线',app.safe_pursuit,'#5856D6','追')
    row(settings,'自动拾取 P / B（安全范围）','优先大 P / B · 火力满后只捡 B',app.collect_power,'#FF3B30','P')
    row(settings,'自动 Bomb','关闭仅决死：预判危险 + 决死补救',app.auto_bomb,'#FF9500','弹',mode_variable=app.deathbomb_only)
    row(settings,'仅预览','显示路线，不发送操作按键',app.preview,'#5AC8FA','览')
    settings=section(left,'修改类')
    row(settings,'无限残机','中弹仍计数 · 关闭后正常消耗',app.infinite_lives,'#FF2D55','命',lambda on:app.change_resource('lives',on))
    row(settings,'无限 Bomb','释放后补充 · 不改变释放时机',app.infinite_bombs,'#FF9500','∞',lambda on:app.change_resource('bombs',on))
    row(settings,'无敌模式','开启 F6 · 关闭 F7',app.god_toggle,'#AF52DE','免',app.change_invincibility)
    training=section(left,'关卡工具 · 修改类')
    choice=tk.Frame(training,bg='white');choice.pack(fill='x',pady=6)
    label(choice,'目标关卡').pack(side='left')
    tk.Spinbox(choice,from_=1,to=6,textvariable=app.training_stage,width=4).pack(side='left',padx=8)
    button(choice,'跳到关卡',lambda:app.training_request(True)).pack(side='right')
    button(training,'重开当前关卡',app.training_request).pack(fill='x',pady=4)
    label(training,'',textvariable=app.training_status,fg=MUTED,wraplength=380,justify='left').pack(fill='x',pady=6)
    learning=section(left,'路线学习 · 实验')
    row(learning,'积累并使用路线经验','道中避弹 + Boss 追击 · 专用路线保持优先',app.learning_enabled,'#34C759','学',separator=False)
    label(learning,'需开启自动射击；道中比较常规走位与回中偏好。无敌、Bomb 干预及中断片段不计奖励。',fg=MUTED,wraplength=380,justify='left').pack(fill='x',pady=6)
    label(learning,'',textvariable=app.learning_status,fg=MUTED,wraplength=380,justify='left').pack(fill='x',pady=6)
    control=section(left,'运行控制')
    label(control,'回到游戏后按 F8 开始 / 停止',font=('Microsoft YaHei UI',11,'bold'),anchor='w').pack(fill='x',padx=6,pady=(7,4))
    label(control,'F9 紧急停止 · Esc 或切出游戏也会停止',fg=MUTED,font=('Microsoft YaHei UI',9),anchor='w').pack(fill='x',padx=6)
    buttons=tk.Frame(control,bg='white');buttons.pack(fill='x',padx=6,pady=12)
    button(buttons,'连接 / 刷新',app.connect,True).pack(side='left',fill='x',expand=True,padx=(0,8))
    button(buttons,'停止控制',lambda:app.stop('已手动停止')).pack(side='left',fill='x',expand=True)
    label(control,'',textvariable=app.status,fg=MUTED,wraplength=400,justify='left',anchor='w',font=('Microsoft YaHei UI',9)).pack(fill='x',padx=6,pady=(0,8))
    protection=section(left,'录像保护')
    label(protection,'使用辅助后禁止保存 Replay',font=('Microsoft YaHei UI',11,'bold'),anchor='w').pack(fill='x',padx=6,pady=(5,6))
    label(protection,'',textvariable=app.replay_status,fg=MUTED,wraplength=400,justify='left',anchor='w',font=('Microsoft YaHei UI',9)).pack(fill='x',padx=6,pady=(0,8))
    preview=section(right,'实时预览')
    app.canvas=tk.Canvas(preview,width=384,height=448,bg='#101025',highlightthickness=0)
    app.canvas.pack(pady=6)
    label(preview,'敌弹 · 橙色敌机 · 蓝色激光 · 黄线避让 · 青点目标',fg=MUTED,font=('Microsoft YaHei UI',9)).pack(pady=(8,6))
    state=section(right,'当前状态')
    label(state,'',textvariable=app.boss_status,fg=MUTED,wraplength=380,justify='left',anchor='w',font=('Microsoft YaHei UI',9)).pack(fill='x',padx=6,pady=8)
    label(state,'',textvariable=app.power_status,fg=MUTED,anchor='w').pack(fill='x',padx=6,pady=8)
    label(state,'',textvariable=app.god_status,fg=MUTED,wraplength=380,justify='left',anchor='w',font=('Microsoft YaHei UI',9)).pack(fill='x',padx=6,pady=8)
    label(state,'拾取让位于避弹，满火力后停止追捡。\nF9 只停止按键控制。无敌和无限资源\n需单独关闭；正常退出时恢复。',fg=MUTED,justify='left',anchor='w',font=('Microsoft YaHei UI',9)).pack(fill='x',padx=6,pady=(0,8))
