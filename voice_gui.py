"""Desktop voice library and local reference-conditioned TTS."""
import copy,datetime,json,os,queue,subprocess,threading,tkinter as tk
from pathlib import Path
from tkinter import filedialog,messagebox,ttk
from tkinter.scrolledtext import ScrolledText
import voice_store as store

ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT/'outputs'
OUTPUT.mkdir(parents=True,exist_ok=True)

class VoiceApp:
    def __init__(self,app,bootstrap=True):
        self.app=app;app.title('AI煮代码汤 · 本地配音与音色库');app.geometry('920x840');app.minsize(820,750)
        self.events=queue.Queue();self.busy=False;self.voices={};self.last_outputs={};self.last_output=None;self.last_created_id=None
        self.presets=json.loads((ROOT/'tuning-presets.json').read_text(encoding='utf-8'))
        outer=ttk.Frame(app,padding=18);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='aicookcode · 本地配音与固定音色',font=('Microsoft YaHei',18,'bold')).pack(anchor='w')
        ttk.Label(outer,text='导入参考录音 → 保存固定音色 → 只换正文生成。参考克隆不训练或改写基础模型。',wraplength=860).pack(anchor='w',pady=(5,12))
        self.tabs=ttk.Notebook(outer);self.tabs.pack(fill='both',expand=True)
        self.generate_page=ttk.Frame(self.tabs,padding=14);self.clone_page=ttk.Frame(self.tabs,padding=14)
        self.tabs.add(self.generate_page,text='  生成配音  ');self.tabs.add(self.clone_page,text='  克隆与音色库  ')
        self.action_buttons=[];self.build_generate();self.build_clone()
        self.status=tk.StringVar(value='正在载入音色库……')
        ttk.Label(outer,textvariable=self.status,wraplength=860).pack(anchor='w',pady=(12,4))
        app.protocol('WM_DELETE_WINDOW',self.close);app.after(150,self.poll)
        if bootstrap:self.background(store.bootstrap,lambda _:self.refresh_voices(),'正在导入已有已认可音色，不重新处理原参考……')
        else:self.refresh_voices()

    def button(self,parent,text,command,**pack):
        b=ttk.Button(parent,text=text,command=command);b.pack(**pack);self.action_buttons.append(b);return b

    def build_generate(self):
        p=self.generate_page
        ttk.Label(p,text='已保存音色：',font=('Microsoft YaHei',11,'bold')).pack(anchor='w')
        bar=ttk.Frame(p);bar.pack(fill='x',pady=(5,8));self.voice_var=tk.StringVar()
        self.voice_box=ttk.Combobox(bar,textvariable=self.voice_var,state='readonly');self.voice_box.pack(side='left',fill='x',expand=True)
        self.voice_box.bind('<<ComboboxSelected>>',self.voice_changed);self.button(bar,'刷新',self.refresh_voices,side='left',padx=(8,0))
        self.info_var=tk.StringVar();ttk.Label(p,textvariable=self.info_var,wraplength=820,foreground='#365e52').pack(anchor='w')
        actions=ttk.Frame(p);actions.pack(fill='x',pady=(10,10))
        for label,handler in [('播放参考',self.play_reference),('查看档案',self.open_profile),('设为默认',self.set_default),('导出备份',self.export_voice),('导入备份',self.import_voice)]:
            self.button(actions,label,handler,side='left',padx=(0,6))
        ttk.Label(p,text='输入新口播正文：').pack(anchor='w')
        self.content=ScrolledText(p,font=('Microsoft YaHei',13),wrap='word',height=13);self.content.pack(fill='both',expand=True,pady=(5,10))
        self.content.insert('1.0','外面的世界很精彩，眼前的生活，也值得用心。')
        ttk.Label(p,text='生成时锁定本档案的参考、文字、模型和参数；需要改变音色或语速，请另存一个新版本。',wraplength=820).pack(anchor='w')
        bar=ttk.Frame(p);bar.pack(fill='x',pady=(12,0))
        self.generate_button=self.button(bar,'使用固定音色生成',lambda:self.generate(False),side='left')
        self.play_button=self.button(bar,'播放最新配音',self.play_latest,side='left',padx=8)
        self.accept_button=self.button(bar,'认可当前音色',self.accept_current,side='left')
        self.button(bar,'打开输出文件夹',lambda:os.startfile(OUTPUT),side='right')

    def build_clone(self):
        p=self.clone_page;p.columnconfigure(1,weight=1)
        self.name_var=tk.StringVar();self.reference_var=tk.StringVar();self.tags_var=tk.StringVar();self.note_var=tk.StringVar()
        ttk.Label(p,text='音色名称').grid(row=0,column=0,sticky='w',pady=4)
        ttk.Entry(p,textvariable=self.name_var).grid(row=0,column=1,sticky='ew',padx=(10,0))
        ttk.Label(p,text='生成模型').grid(row=1,column=0,sticky='w',pady=5)
        self.engine_var=tk.StringVar(value='Qwen · 本地首选')
        self.engine_box=ttk.Combobox(p,textvariable=self.engine_var,state='readonly',values=['Qwen · 本地首选','ZipVoice · 仅非商业测试'])
        self.engine_box.grid(row=1,column=1,sticky='ew',padx=(10,0));self.engine_box.bind('<<ComboboxSelected>>',self.reset_recipe)
        ttk.Label(p,text='参考录音').grid(row=2,column=0,sticky='w',pady=5)
        row=ttk.Frame(p);row.grid(row=2,column=1,sticky='ew',padx=(10,0));row.columnconfigure(0,weight=1)
        ttk.Entry(row,textvariable=self.reference_var).grid(row=0,column=0,sticky='ew')
        b=ttk.Button(row,text='选择文件',command=self.choose_reference);b.grid(row=0,column=1,padx=(6,0));self.action_buttons.append(b)
        ttk.Label(p,text='选取片段').grid(row=3,column=0,sticky='w')
        row=ttk.Frame(p);row.grid(row=3,column=1,sticky='w',padx=(10,0),pady=5)
        self.start_var=tk.StringVar(value='0');self.duration_var=tk.StringVar(value='8')
        ttk.Label(row,text='从第').pack(side='left');ttk.Entry(row,textvariable=self.start_var,width=7).pack(side='left',padx=4)
        ttk.Label(row,text='秒开始，取').pack(side='left');ttk.Entry(row,textvariable=self.duration_var,width=7).pack(side='left',padx=4)
        ttk.Label(row,text='秒（2–30秒，先选5–10秒完整句）').pack(side='left')
        ttk.Label(p,text='参考文字').grid(row=4,column=0,sticky='nw',pady=6)
        self.transcript=ScrolledText(p,font=('Microsoft YaHei',11),height=3,wrap='word');self.transcript.grid(row=4,column=1,sticky='ew',padx=(10,0),pady=5)
        self.reference_help=tk.StringVar();ttk.Label(p,textvariable=self.reference_help,wraplength=720,foreground='#655744').grid(row=5,column=1,sticky='w',padx=(10,0))
        ttk.Label(p,text='标签 / 备注').grid(row=6,column=0,sticky='w',pady=5)
        row=ttk.Frame(p);row.grid(row=6,column=1,sticky='ew',padx=(10,0));row.columnconfigure(1,weight=1)
        ttk.Entry(row,textvariable=self.tags_var,width=24).grid(row=0,column=0,padx=(0,8));ttk.Entry(row,textvariable=self.note_var).grid(row=0,column=1,sticky='ew')
        panel=ttk.LabelFrame(p,text='固定参数（默认沿用已选方案；改参数请另存版本）',padding=8)
        panel.grid(row=7,column=0,columnspan=2,sticky='nsew',pady=(10,8));p.rowconfigure(7,weight=1)
        rate=ttk.Frame(panel);rate.pack(fill='x',pady=(0,6));self.speed_var=tk.StringVar(value='0.95')
        ttk.Label(rate,text='语速（存入音色档案）：').pack(side='left')
        ttk.Spinbox(rate,textvariable=self.speed_var,from_=.85,to=1.15,increment=.01,width=7).pack(side='left')
        ttk.Label(rate,text='  1.00 为原速；以下高级参数可保持默认。').pack(side='left')
        self.recipe=ScrolledText(panel,font=('Consolas',10),height=5,wrap='word');self.recipe.pack(fill='both',expand=True)
        row=ttk.Frame(p);row.grid(row=8,column=0,columnspan=2,sticky='ew',pady=5)
        self.button(row,'从当前音色复制',self.clone_current,side='left');self.button(row,'恢复该模型参数',self.reset_recipe,side='left',padx=7)
        self.button(row,'保存固定音色',self.save_voice,side='right')
        row=ttk.LabelFrame(p,text='用新文字试听已保存的音色',padding=8);row.grid(row=9,column=0,columnspan=2,sticky='ew',pady=5);row.columnconfigure(0,weight=1)
        self.preview_var=tk.StringVar(value='今天，给自己一点从容。把眼前的日子，过得踏实而温暖。')
        ttk.Entry(row,textvariable=self.preview_var).grid(row=0,column=0,sticky='ew')
        b=ttk.Button(row,text='生成试听',command=self.preview_saved);b.grid(row=0,column=1,padx=6);self.action_buttons.append(b)
        self.saved_hint=tk.StringVar(value='先保存音色。修改表单后须再次保存，试听使用最后保存的档案。')
        ttk.Label(p,textvariable=self.saved_hint,wraplength=820).grid(row=10,column=0,columnspan=2,sticky='w',pady=5)
        self.reset_recipe()

    def reset_recipe(self,event=None):
        engine='qwen' if self.engine_var.get().startswith('Qwen') else 'zipvoice'
        cfg=copy.deepcopy(self.presets[store.BUILTINS[engine]])
        for k in ['reference','reference_text']:cfg.pop(k,None)
        self.recipe_base=cfg;self.speed_var.set(f"{cfg.get('default_speed',1.):.2f}");self.show_recipe(cfg)
        self.reference_help.set('Qwen 本运行器不读取参考文字；可填写并保存，供归档与迁移。' if engine=='qwen' else 'ZipVoice 必填：文字须与截取片段逐字一致。当前 Emilia 权重仅限非商业测试。')

    def show_recipe(self,cfg):
        keys=['seed','temperature','top_p','repeat_penalty','chunk_limit','max_frames','gap_seconds','steps','guidance_scale','minimum_chars','maximum_chars','threads','light_denoise','denoise_nr','denoise_highpass_hz','denoise_lowpass_hz']
        self.recipe.delete('1.0','end');self.recipe.insert('1.0',json.dumps({k:cfg[k] for k in keys if k in cfg},ensure_ascii=False,indent=2))

    def choose_reference(self):
        path=filedialog.askopenfilename(title='选择参考录音',filetypes=[('音频','*.wav *.mp3 *.m4a *.flac *.ogg'),('全部文件','*.*')])
        if path:self.reference_var.set(path)

    def current_id(self):
        if self.voice_var.get() not in self.voices:raise ValueError('请先选择已保存音色。')
        return self.voices[self.voice_var.get()]['id']

    def refresh_voices(self,prefer=None):
        if not isinstance(prefer,str):prefer=None
        try:old=self.current_id()
        except ValueError:old=None
        ix=store.index();self.voices={f"{v['name']}  [{'已认可' if v['accepted'] else '待试听'} · {v['id'][:6]}]":v for v in ix['voices']}
        self.voice_box.config(values=list(self.voices));selected=prefer or old or ix['default_id']
        self.voice_var.set(next((label for label,v in self.voices.items() if v['id']==selected),next(iter(self.voices),'')));self.voice_changed()

    def voice_changed(self,event=None):
        try:
            vid=self.current_id();entry,p,cfg=store.get_voice(vid,verify_models=False)
            default=' · 默认音色' if store.index()['default_id']==vid else '';license_note=' · 仅非商业测试' if p['engine']=='zipvoice' else ''
            self.info_var.set(f"已锁定：{p['engine']} / 语速 {cfg.get('default_speed',1):.2f} / 参考 {p['reference_info']['seconds']:.2f}秒{default}{license_note}\n参考、转写和参数随档案保存；生成前校验关键模型与运行器文件。")
            self.status.set('已载入固定音色。新稿只需更换正文。')
        except Exception as e:self.info_var.set(str(e));self.status.set('音色未就绪：'+str(e))
        self.update_buttons()

    def update_buttons(self):
        if self.busy:return
        try:vid=self.current_id()
        except ValueError:vid=None
        self.play_button.config(state='normal' if self.last_output else 'disabled')
        self.accept_button.config(state='normal' if vid in self.last_outputs else 'disabled')
        self.generate_button.config(state='normal' if vid else 'disabled')

    def background(self,work,done,status):
        if self.busy:return
        self.busy=True;self.status.set(status)
        for b in self.action_buttons:b.config(state='disabled')
        self.voice_box.config(state='disabled');self.engine_box.config(state='disabled')
        def run():
            try:self.events.put(('done',done,work()))
            except Exception as e:self.events.put(('error',None,str(e)))
        threading.Thread(target=run,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,callback,value=self.events.get_nowait()
                if kind=='progress':self.status.set(value);continue
                self.busy=False
                for b in self.action_buttons:b.config(state='normal')
                self.voice_box.config(state='readonly');self.engine_box.config(state='readonly')
                try:
                    if kind=='done':callback(value)
                    else:self.status.set(value);messagebox.showerror('操作未完成',value)
                except Exception as e:
                    self.status.set(str(e));messagebox.showerror('操作未完成',str(e))
                self.update_buttons()
        except queue.Empty:pass
        self.app.after(150,self.poll)

    def clone_current(self):
        try:
            _,p,cfg=store.get_voice(self.current_id(),verify_models=False)
            self.engine_var.set('Qwen · 本地首选' if p['engine']=='qwen' else 'ZipVoice · 仅非商业测试');self.reset_recipe()
            self.name_var.set(p['name']+' v2');self.reference_var.set(cfg['reference']);self.start_var.set('0');self.duration_var.set(f"{p['reference_info']['seconds']:.5f}")
            self.transcript.delete('1.0','end');self.transcript.insert('1.0',Path(cfg['reference_text']).read_text(encoding='utf-8'))
            self.recipe_base=copy.deepcopy(p['settings']);self.speed_var.set(f"{p['settings'].get('default_speed',1.):.2f}");self.show_recipe(p['settings'])
            self.tags_var.set(p.get('tags',''));self.note_var.set('复制当前档案；改动后另存新版本');self.tabs.select(self.clone_page)
        except Exception as e:messagebox.showerror('无法复制音色',str(e))

    def save_voice(self):
        try:
            engine='qwen' if self.engine_var.get().startswith('Qwen') else 'zipvoice'
            cfg=copy.deepcopy(self.recipe_base);cfg.update(json.loads(self.recipe.get('1.0','end')));cfg['default_speed']=float(self.speed_var.get())
            cfg=store.validate_settings(engine,cfg)
            params=dict(name=self.name_var.get().strip(),engine=engine,reference=self.reference_var.get(),transcript=self.transcript.get('1.0','end').strip(),settings=cfg,start=float(self.start_var.get()),duration=float(self.duration_var.get()),tags=self.tags_var.get(),note=self.note_var.get())
            if not params['name']:raise ValueError('请填写音色名称。')
            if not Path(params['reference']).is_file():raise ValueError('请先选择参考录音。')
            if engine=='zipvoice' and not params['transcript']:raise ValueError('ZipVoice 必须填写参考文字。')
        except Exception as e:messagebox.showerror('请检查音色设置',str(e));return
        def done(entry):
            self.last_created_id=entry['id'];self.refresh_voices(entry['id']);_,p,_=store.get_voice(entry['id'],verify_models=False)
            warning=' 参考存在满幅采样，建议复听原录音。' if p['reference_info']['clipped_samples'] else ''
            self.saved_hint.set('已保存：'+entry['name']+'。点击生成试听；满意后在生成页认可并设为默认。'+warning)
            self.status.set('已保存独立音色档案，未覆盖已有音色。')
        self.background(lambda:store.create_voice(**params),done,'正在截取、校验并保存固定音色……')

    def preview_saved(self):
        if not self.last_created_id:messagebox.showinfo('先保存音色','请先保存当前克隆设置，再生成试听。');return
        self.generate(True,self.last_created_id)

    def generate(self,preview=False,voice_id=None):
        try:
            vid=voice_id or self.current_id();entry,p,cfg=store.get_voice(vid,verify_models=False)
            content=self.preview_var.get().strip() if preview else self.content.get('1.0','end').strip()
            if not content or len(content)>5000:raise ValueError('请输入 1–5000 字的口播正文。')
            profile=store.profile_path(vid);exe=store.python_path(p['engine'])
        except Exception as e:messagebox.showerror('无法生成',str(e));return
        stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');script=OUTPUT/f"{stamp}-{'试听' if preview else '配音'}-{p['engine']}.txt"
        dest=script.with_suffix('.wav');script.write_text(content,encoding='utf-8')
        def work():
            env=os.environ.copy();env.update(PYTHONUTF8='1',OMP_NUM_THREADS='6')
            args=[str(exe),'-u',str(ROOT/'local_voice.py'),'--voice-profile',str(profile),'--profile-hash',entry['profile_sha256'],'--text-file',str(script),'--out',str(dest)]
            with script.with_suffix('.log').open('w',encoding='utf-8') as log:
                proc=subprocess.Popen(args,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for line in proc.stdout:log.write(line);log.flush();self.events.put(('progress',None,line.strip()))
                code=proc.wait()
            if code:raise RuntimeError('生成失败，详情见输出文件夹内同名日志。')
            return dest
        def done(path):
            self.last_output=path;self.last_outputs[vid]=path;self.refresh_voices(vid);self.status.set('已按固定档案生成：'+path.name)
        self.background(work,done,'正在校验固定音色并生成新文字……')

    def play_reference(self):
        try:_,_,cfg=store.get_voice(self.current_id(),verify_models=False);os.startfile(cfg['reference'])
        except Exception as e:messagebox.showerror('无法播放',str(e))

    def play_latest(self):
        if self.last_output and self.last_output.is_file():os.startfile(self.last_output)

    def open_profile(self):
        try:os.startfile(store.profile_path(self.current_id()))
        except Exception as e:messagebox.showerror('无法打开',str(e))

    def set_default(self):
        try:vid=self.current_id();store.set_default(vid);self.refresh_voices(vid);self.status.set('默认音色已保存，下次启动会自动选中。')
        except Exception as e:messagebox.showerror('无法设为默认',str(e))

    def accept_current(self):
        try:vid=self.current_id();store.mark_accepted(vid,self.last_outputs[vid]);self.refresh_voices(vid);self.status.set('已记录人工认可；点击“设为默认”可在下次启动自动使用。')
        except Exception as e:messagebox.showerror('无法记录认可',str(e))

    def export_voice(self):
        try:vid=self.current_id()
        except ValueError as e:messagebox.showerror('请选择音色',str(e));return
        dest=filedialog.asksaveasfilename(title='导出固定音色备份',defaultextension='.zip',initialfile='固定音色-'+vid[:6]+'.zip',filetypes=[('音色备份','*.zip')])
        if dest:self.background(lambda:store.export_voice(vid,dest),lambda p:self.status.set('已导出音色备份：'+str(p)),'正在导出参考、文字与固定参数……')

    def import_voice(self):
        source=filedialog.askopenfilename(title='导入固定音色备份',filetypes=[('音色备份','*.zip')])
        if not source:return
        def done(entry):self.refresh_voices(entry['id']);self.last_created_id=entry['id'];self.saved_hint.set('已导入副本：'+entry['name']+'；请重新试听确认。');self.status.set('备份已校验并导入，已有音色未覆盖。')
        self.background(lambda:store.import_voice(source),done,'正在核对备份与模型版本……')

    def close(self):
        if self.busy:messagebox.showinfo('正在处理','请等待当前操作结束后关闭窗口。');return
        self.app.destroy()

def main():
    root=tk.Tk();VoiceApp(root);root.mainloop()

if __name__=='__main__':main()
