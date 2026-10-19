"""Pinned CPU TTS model installer. Does not modify global Python packages."""
import argparse,hashlib,json,os,pathlib,shutil,struct,subprocess,sys,tarfile,time,urllib.request,venv,zipfile
ROOT=pathlib.Path(__file__).resolve().parent
# Keep pip output readable for Chinese paths, including redirected terminals.
os.environ['PYTHONUTF8']='1'
os.environ['PYTHONIOENCODING']='utf-8'
if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8')

def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def download(item):
    p=ROOT/item['relative'];p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        if digest(p)==item['sha256']:print('Verified:',p.name,flush=True);return p
        raise RuntimeError('Existing file hash mismatch; preserved, please inspect: '+str(p))
    partial=p.with_name(p.name+'.part')
    if partial.exists():raise RuntimeError('Previous incomplete download preserved. Rename it before retrying: '+str(partial))
    request=urllib.request.Request(item['url'],headers={'User-Agent':'LocalTTS-Repro/1.0'})
    total=0;last=time.monotonic()
    with urllib.request.urlopen(request,timeout=90) as response,partial.open('xb') as out:
        while block:=response.read(1024*1024):
            out.write(block);total+=len(block)
            if time.monotonic()-last>10:print(p.name,round(total/2**20,1),'MiB',flush=True);last=time.monotonic()
    if total!=item['bytes'] or digest(partial)!=item['sha256']:
        raise RuntimeError('Download verification failed; partial preserved: '+str(partial))
    partial.rename(p);print('Downloaded:',p.name,flush=True);return p

def verify(root,engine):
    checks=json.loads((ROOT/'installed-files.json').read_text(encoding='utf-8'))
    chosen=[(p,h) for p,h in checks.items() if engine=='all' or ('qwen' in p)==(engine=='qwen')]
    for rel,expected in chosen:
        p=root/rel
        if not p.is_file() or digest(p)!=expected:raise RuntimeError('Missing or different file: '+str(p))
        print('Verified:',rel,flush=True)
    return len(chosen)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--engine',choices=['all','qwen','zipvoice'],default='all');ap.add_argument('--verify-root',type=pathlib.Path);ap.add_argument('--pinned-deps',action='store_true',help='Use the original tested dependency versions');args=ap.parse_args()
    if args.verify_root:
        print('Verified installed files:',verify(args.verify_root,args.engine));return
    if os.name!='nt' or struct.calcsize('P')!=8:
        raise RuntimeError('Windows 64-bit Python is required by the bundled runtime.')
    if sys.version_info < (3,11):
        raise RuntimeError('Python 3.11 or newer is required. Run with: py -3.11 install_models.py')
    print('Using Python:',sys.version.split()[0],sys.executable,flush=True)
    import tkinter
    space=shutil.disk_usage(ROOT).free/2**30
    if space<4:raise RuntimeError('Less than 4 GiB free. Please use a drive with at least 8 GiB available.')
    env=ROOT/'.venv'
    if not (env/'Scripts/python.exe').exists():venv.create(env,with_pip=True)
    py=env/'Scripts/python.exe'
    env_version=json.loads(subprocess.check_output([str(py),'-c','import json,sys; print(json.dumps(list(sys.version_info[:2])))'],text=True,encoding='utf-8'))
    if tuple(env_version)!=sys.version_info[:2]:
        raise RuntimeError('Existing .venv uses Python '+'.'.join(map(str,env_version))+'. Run the installer with that Python, or rename .venv to keep it as a backup before switching versions.')
    subprocess.run([str(py),'-m','pip','install','--upgrade','pip'],check=True)
    requirements=ROOT/('requirements.txt' if args.pinned_deps else 'requirements-compatible.txt')
    try:
        subprocess.run([str(py),'-m','pip','install','--only-binary=:all:','-r',str(requirements)],check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError('Dependencies could not be installed for this Python. Check the pip error above for network or missing wheels. Try Python 3.11 or 3.13 if this version is unsupported.') from exc
    (ROOT/'installed-dependencies.txt').write_text(subprocess.check_output([str(py),'-m','pip','freeze'],text=True,encoding='utf-8'),encoding='utf-8')
    ff=subprocess.check_output([str(py),'-c','import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'],text=True,encoding='utf-8').strip()
    (ROOT/'bin').mkdir(exist_ok=True);target=ROOT/'bin/ffmpeg.exe'
    if not target.exists():shutil.copy2(ff,target)
    items=json.loads((ROOT/'downloads.json').read_text(encoding='utf-8'))
    for item in items:
        is_qwen='qwen06' in item['relative']
        if args.engine!='all' and is_qwen!=(args.engine=='qwen'):continue
        p=download(item)
        if p.name=='runtime.zip':
            dest=p.parent/'runtime'
            if not (dest/'llama-tts.exe').exists():
                with zipfile.ZipFile(p) as z:
                    for n in z.namelist():
                        resolved=(dest/n).resolve()
                        if not resolved.is_relative_to(dest.resolve()):raise RuntimeError('Unsafe archive path')
                    z.extractall(dest)
        if p.name=='zip-fp32.tar.bz2':
            dest=ROOT/'candidates/zipvoice-fp32';dest.mkdir(parents=True,exist_ok=True)
            if not (dest/'sherpa-onnx-zipvoice-distill-fp32-zh-en-emilia/lexicon.txt').exists():
                with tarfile.open(p) as z:z.extractall(dest,filter='data')
    verify(ROOT,args.engine)
    (ROOT/'installation-ok.json').write_text(json.dumps({'python':sys.version,'engine':args.engine,'installed_at':time.strftime('%Y-%m-%dT%H:%M:%S'),'all_selected_model_hashes_verified':True},indent=2),encoding='utf-8')
    print('READY. Open the launcher, or: .venv\\Scripts\\python.exe voice_gui.py',flush=True)

if __name__=='__main__':main()
