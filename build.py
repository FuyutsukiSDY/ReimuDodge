from pathlib import Path
import subprocess,sys,json,hashlib,shutil
ROOT=Path(__file__).resolve().parent
WORK=ROOT/'build'
def pack(name,source,entry,extra=()):
 w=WORK/name;w.mkdir(parents=True,exist_ok=True)
 cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--onefile','--windowed','--name','自动档灵梦','--icon',str(source/'reimu.ico'),'--add-data',str(source/'reimu.ico')+';.',*extra,'--distpath',str(w/'dist'),'--workpath',str(w/'cache'),'--specpath',str(w),str(source/entry)]
 with (w/'build.log').open('w',encoding='utf8') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
 return w/'dist/自动档灵梦.exe'
if __name__=='__main__':
 payload=ROOT/'launcher/payloads';payload.mkdir(exist_ok=True);manifest={}
 for edition in ('classic','new'):
  # Distribution build may reuse the byte-identical V2 classic payload.
  frozen=ROOT/'classic-original.exe'
  exe=frozen if edition=='classic' and frozen.exists() else pack(edition,ROOT/edition,'app.py',['--add-binary',str(ROOT/edition/'core.dll')+';.'] if edition=='new' else [])
  dest=payload/(edition+'.exe');shutil.copy2(exe,dest)
  manifest[edition]=dict(version='2.0' if edition=='classic' else '3.0',sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),replay_protection=True)
 (ROOT/'launcher/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
 exe=pack('launcher',ROOT/'launcher','launcher.py',['--add-data',str(ROOT/'launcher/manifest.json')+';.','--add-data',str(payload)+';payloads'])
 dist=ROOT/'dist';dist.mkdir(exist_ok=True);shutil.copy2(exe,dist/'自动档灵梦.exe')
 print(dist)
