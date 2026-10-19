"""Offline, fixed-reference TTS. No account, cloud request, or secret is required."""
import argparse,hashlib,json,os,pathlib,re,subprocess,time,wave
ROOT=pathlib.Path(__file__).resolve().parent
PROFILE=ROOT/'profiles'/'aicookcode-local-test'
def chunks(text,limit=44):
 answer=[]
 for paragraph in text.splitlines():
  parts=re.findall(r'[^。！？!?；;]+[。！？!?；;]?',paragraph)
  pending=''
  for part in parts:
   part=part.strip()
   if pending and len(pending)+len(part)>limit:answer.append(pending);pending=''
   while len(part)>limit:
    split=max(part.rfind(p,0,limit+1) for p in '，,:：、 ')
    if split<limit//2:split=limit-1
    answer.append(part[:split+1].strip());part=part[split+1:].strip()
   pending+=part
  if pending:answer.append(pending)
 return answer
def synthesize(engine,text,out,preset='baseline',speed=None,voice_profile=None,profile_hash=None):
 settings={}
 fixed_profile=None
 if voice_profile:
  from voice_store import load_profile,sha256 as profile_sha
  fixed_profile,settings=load_profile(voice_profile,expected_profile_hash=profile_hash)
  if engine and engine!=fixed_profile['engine']:raise ValueError('模型与固定音色档案不匹配。')
  engine=fixed_profile['engine'];preset='saved-voice-profile'
  if speed is not None and speed!=settings.get('default_speed',1.):raise ValueError('固定音色已锁定语速；请在音色管理中另存为新版本。')
 elif preset!='baseline':
  presets=json.loads((ROOT/'tuning-presets.json').read_text(encoding='utf-8'))
  if preset not in presets or presets[preset]['engine']!=engine:raise ValueError('调音模式与模型不匹配。')
  settings=presets[preset]
 speed=settings.get('default_speed',1.) if speed is None else speed
 if not .85<=speed<=1.15:raise ValueError('语速请设在0.85至1.15之间。')
 ref_path=ROOT/settings['reference'] if settings.get('reference') else PROFILE/'reference.wav'
 out=pathlib.Path(out).resolve();out.parent.mkdir(parents=True,exist_ok=True)
 if out.exists():raise FileExistsError('输出文件已存在，请换一个文件名，以免覆盖。')
 if len(text.strip())==0:raise ValueError('请填写口播正文。')
 if len(text)>5000:raise ValueError('单次请不超过5000字。')
 start=time.monotonic();records=[]
 work=out.parent/(out.stem+'-parts');work.mkdir(exist_ok=True)
 if engine=='qwen':
  c=ROOT/'candidates'/'qwen06-llamacpp'
  env=os.environ.copy();env.update(HF_HOME=str(c/'cache'),LLAMA_CACHE=str(c/'cache'),OMP_NUM_THREADS='6')
  parts=chunks(text,settings.get('chunk_limit',44))
  for i,part in enumerate(parts,1):
   wav=work/f'{i:03d}.wav'
   limit=settings.get('max_frames',300)
   # The native CLI's fopen is not Unicode-aware on Windows. An ASCII
   # relative output name keeps Chinese user-selected folders working.
   args=[str(c/'runtime'/'llama-tts.exe'),'-m',str(c/'model.gguf'),'-mm',str(c/'mmproj.gguf'),'--offline','--tts-lang','zh','--tts-speaker-file',str(ref_path),'-p',part,'-o',wav.name,'-t','6','-tb','6','-ngl','0','--no-mmproj-offload','-c','1024','-b','128','-ub','128','-n',str(limit),'--seed',str(settings.get('seed',20261017)),'--temp',str(settings.get('temperature',.7)),'--top-k','50','--top-p',str(settings.get('top_p',1.)),'--min-p','0','--repeat-penalty',str(settings.get('repeat_penalty',1.05))]
   t=time.monotonic()
   with open(work/f'{i:03d}.log','w',encoding='utf-8') as f:subprocess.run(args,cwd=work,env=env,stdout=f,stderr=f,timeout=300,check=True)
   with wave.open(str(wav)) as f:duration=f.getnframes()/f.getframerate()
   if duration>=limit*.08-.1:raise RuntimeError('该句达到安全时长上限，请检查分段，未输出成品。')
   records.append(dict(text=part,elapsed_s=round(time.monotonic()-t,3),audio_s=duration))
   print(f'完成 {i}/{len(parts)}',flush=True)
 else:
  import sherpa_onnx
  import soundfile as sf
  c=ROOT/'candidates'/'zipvoice-int8'
  m=ROOT/settings['model_directory'] if settings.get('model_directory') else c/'sherpa-onnx-zipvoice-distill-int8-zh-en-emilia'
  encoder=m/settings['encoder_file'] if settings.get('encoder_file') else next(m.glob('encoder*.onnx'))
  decoder=m/settings['decoder_file'] if settings.get('decoder_file') else next(m.glob('decoder*.onnx'))
  if not (m/'lexicon.txt').is_file():raise FileNotFoundError('缺少中文发音词典，已停止生成，避免漏读中文。')
  cfg=sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(zipvoice=sherpa_onnx.OfflineTtsZipvoiceModelConfig(tokens=str(m/'tokens.txt'),encoder=str(encoder),decoder=str(decoder),data_dir=str(m/'espeak-ng-data'),lexicon=str(m/'lexicon.txt'),vocoder=str(c/'vocos_24khz.onnx')),num_threads=settings.get('threads',6),provider='cpu'))
  if not cfg.validate():raise RuntimeError('模型文件校验失败。')
  tts=sherpa_onnx.OfflineTts(cfg)
  ref,sr=sf.read(ref_path,dtype='float32')
  ref_text_path=ROOT/settings['reference_text'] if settings.get('reference_text') else PROFILE/'transcript.txt'
  gc=sherpa_onnx.GenerationConfig();gc.reference_audio=ref;gc.reference_sample_rate=sr;gc.reference_text=ref_text_path.read_text(encoding='utf-8');gc.num_steps=settings.get('steps',4);gc.speed=speed;gc.silence_scale=1.
  gc.extra={'min_char_in_sentence':str(settings.get('minimum_chars',30)),'max_char_in_sentence':str(settings.get('maximum_chars',80)),'guidance_scale':str(settings.get('guidance_scale',1.))}
  # Longer coherent paragraphs give ZipVoice more prosodic context.
  for i,part in enumerate(chunks(text,settings.get('chunk_limit',80)),1):
   t=time.monotonic();audio=tts.generate(part,gc)
   if not len(audio.samples):raise RuntimeError('模型返回空音频。')
   import numpy as np
   samples=np.asarray(audio.samples,dtype=np.float32);raw_peak=float(np.max(np.abs(samples)));peak_scale=min(1.,.97/max(raw_peak,1e-9)) if settings else 1.
   sf.write(work/f'{i:03d}.wav',samples*peak_scale,audio.sample_rate,subtype='PCM_16')
   records.append(dict(text=part,elapsed_s=round(time.monotonic()-t,3),audio_s=len(audio.samples)/audio.sample_rate,raw_peak=raw_peak,peak_scale=peak_scale));print(f'完成分段 {i}',flush=True)
 wavs=sorted(work.glob('*.wav'))
 if len(wavs)!=len(records):raise RuntimeError('分段数量异常，请选择新的输出名称。')
 with wave.open(str(wavs[0])) as f:params=f.getparams()
 with wave.open(str(out),'wb') as target:
  target.setparams(params)
  for i,p in enumerate(wavs):
   with wave.open(str(p)) as f:
    if (f.getnchannels(),f.getsampwidth(),f.getframerate())!=(params.nchannels,params.sampwidth,params.framerate):raise RuntimeError('音频规格不一致。')
    target.writeframes(f.readframes(f.getnframes()))
   if i<len(wavs)-1:target.writeframes(bytes(round(settings.get('gap_seconds',.15)*params.framerate)*params.nchannels*params.sampwidth))
 filters=[]
 if engine=='qwen' and speed!=1.:filters.append(f'atempo={speed}')
 if settings.get('light_denoise'):
  filters.extend([f"highpass=f={settings.get('denoise_highpass_hz',65)}",f"afftdn=nr={settings.get('denoise_nr',6)}:nf=-40:tn=1:gs=5",f"lowpass=f={settings.get('denoise_lowpass_hz',10000)}"])
 if filters:
  processed=work/'postprocessed.wav';ff=ROOT/'bin'/'ffmpeg.exe'
  subprocess.run([str(ff),'-y','-hide_banner','-loglevel','error','-i',str(out),'-af',','.join(filters),'-ar',str(params.framerate),'-c:a','pcm_s16le',str(processed)],check=True,timeout=180)
  os.replace(processed,out)
 with wave.open(str(out)) as f:duration=f.getnframes()/f.getframerate()
 if fixed_profile:
  # Detect changes during a multi-paragraph generation as well as before it.
  load_profile(voice_profile,expected_profile_hash=profile_hash)
 manifest=dict(engine=engine,preset=preset,speed=speed,settings=settings,postprocess_filters=filters,voice=fixed_profile['name'] if fixed_profile else 'aicookcode-local-test',reference_sha256=hashlib.file_digest(open(ref_path,'rb'),'sha256').hexdigest(),text=text,elapsed_s=round(time.monotonic()-start,3),audio_s=duration,parts=records,output_sha256=hashlib.file_digest(open(out,'rb'),'sha256').hexdigest(),note='参考条件生成，未训练或改写基础模型。')
 if fixed_profile:
  manifest['voice_profile']={'id':fixed_profile['id'],'name':fixed_profile['name'],'path':str(pathlib.Path(voice_profile).resolve()),'profile_sha256':profile_sha(voice_profile),'settings_sha256':fixed_profile['settings_sha256'],'model_sha256':fixed_profile['model_sha256'],'transcript_sha256':fixed_profile['transcript_sha256'],'identity_locked':True}
 out.with_suffix('.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 print('已保存：'+str(out),flush=True)
 return manifest
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--engine',choices=['qwen','zipvoice']);ap.add_argument('--text-file',required=True);ap.add_argument('--out',required=True);ap.add_argument('--preset',default='baseline');ap.add_argument('--speed',type=float,default=None);ap.add_argument('--voice-profile');ap.add_argument('--profile-hash');a=ap.parse_args()
 if not a.engine and not a.voice_profile:ap.error('请提供 --engine 或 --voice-profile')
 synthesize(a.engine,pathlib.Path(a.text_file).read_text(encoding='utf-8-sig'),a.out,a.preset,a.speed,a.voice_profile,a.profile_hash)
