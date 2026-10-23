"""Trusted local, one-shot offline supervisor. --check never samples or executes history."""
from pathlib import Path
import datetime,hashlib,importlib.util,json,os,resource,selectors,signal,subprocess,sys,time
from verify import ROOT,WS,read,sha,static
PY='/opt/homebrew/Cellar/python@3.15/3.15.0/Frameworks/Python.framework/Versions/3.15/bin/python3.15'
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def store(path,value):
 with Path(path).open('x') as f:
  json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 d=os.open(Path(path).parent,os.O_RDONLY)
 try:os.fsync(d)
 finally:os.close(d)
def authority(raw,b,now):
 assert len(raw)<16384,'AUTHORITY_SIZE'
 a=json.loads(raw)
 assert a.get('founderApproved') is True and a.get('domain')=='SAVED_EXPLORATORY_NATIVE_PAIR','DIRECT_FOUNDER_APPROVAL_REQUIRED'
 assert a.get('operationCommitment')==b['operationCommitment'] and a.get('binarySha256')==b['binarySha256'],'EXACT_AUTHORITY_REQUIRED'
 assert a.get('maximumInvocations')=={'ACTUAL':1,'BRANCH':1,'B':0} and a.get('RPC')==a.get('WSS')==0,'AUTHORITY_SCOPE'
 assert a.get('runtimePath')==str(ROOT/'runtime') and a.get('archivePath')==b['archivePath'],'EXACT_OUTPUT_PATHS'
 assert a.get('notBeforeUnix',now+1)<=now and a.get('expiresUnix',0)-now>=140 and a['expiresUnix']-a['notBeforeUnix']<=600,'AUTHORITY_WINDOW'
 assert a.get('macOnPowerOpenLid') is True and a.get('noRetry') is True,'HOST_AND_NO_RETRY_CONFIRMATION'
 assert a.get('executionContext')==b.get('executionContext')=='require_escalated','EXACT_APPROVED_EXECUTION_CONTEXT_REQUIRED'
 return a
def sample_owned(proc):
 # Only our exact newly spawned worker. No argv/environment, unrelated metrics.
 p=subprocess.run(['/bin/ps','-p',str(proc.pid),'-o','pid=,ppid=,pgid=,rss=,comm='],capture_output=True,text=True,timeout=1)
 if not p.stdout.strip():
  assert proc.poll() is not None,'OWNED_TELEMETRY_MISSING'
  return None
 rows=p.stdout.strip().splitlines();assert p.returncode==0 and len(rows)==1
 pid,ppid,pgid,rss,comm=rows[0].strip().split(None,4)
 assert int(pid)==proc.pid and int(ppid)==os.getpid() and int(pgid)==proc.pid,'OWNED_PROCESS_IDENTITY'
 assert Path(comm).name=='rhook-saved-pair','WORKER_EXECUTABLE_IDENTITY'
 return {'pid':int(pid),'ppid':int(ppid),'pgid':int(pgid),'executable':comm,'rssBytes':int(rss)*1024}
def monitored(raw,rt,limits):
 assert limits['pairWallSeconds']==limits['workerKernelCpuSeconds']==120 and limits['workerSampledRssBytes']==4<<30,'EXACT_REVIEWED_PAIR_LIMITS'
 assert limits['workerTelemetryMs']==100 and limits['maximumTelemetryGapSeconds']==2,'EXACT_TELEMETRY_LIMITS'
 def caps():
  resource.setrlimit(resource.RLIMIT_CPU,(120,120));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
  resource.setrlimit(resource.RLIMIT_FSIZE,(64<<20,64<<20));resource.setrlimit(resource.RLIMIT_NOFILE,(256,256))
 env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','TZ':'UTC','GOMAXPROCS':'2','GOMEMLIMIT':'1073741824','GOTRACEBACK':'single'}
 proc=None;selector=selectors.DefaultSelector();files={};stop=None;captured=0;peak=0;samples=0;began=time.monotonic();last=None;old={}
 before=resource.getrusage(resource.RUSAGE_CHILDREN);interrupted=[]
 try:
  for sig in [signal.SIGTERM,signal.SIGINT]:old[sig]=signal.signal(sig,lambda s,f:interrupted.append(s))
  for name in ['stdout','stderr']:files[name]=(rt/(name+'.log')).open('xb')
  telemetry=(rt/'RESOURCES.jsonl').open('x')
  proc=subprocess.Popen([str(ROOT/'artifacts/rhook-saved-pair'),'--execute-once'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=ROOT,env=env,start_new_session=True,preexec_fn=caps)
  store(rt/'PROCESS_STARTED.json',{'pid':proc.pid,'pgid':proc.pid,'executable':str(ROOT/'artifacts/rhook-saved-pair'),'utc':utc(),'kernelCpuSeconds':120,'automaticRetry':False})
  proc.stdin.write(raw);proc.stdin.close()
  for name,stream in [('stdout',proc.stdout),('stderr',proc.stderr)]:os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,name)
  while proc.poll() is None or selector.get_map():
   now=time.monotonic()
   if now-began>120:stop='PAIR_WALL_TIME_LIMIT'
   if interrupted:stop='EXTERNAL_SIGNAL'
   if proc.poll() is None:
    if last is not None and now-last>2:stop='RESOURCE_TELEMETRY_GAP'
    row=sample_owned(proc);ended=time.monotonic()
    if ended-now>2 or last is not None and ended-last>2:stop='RESOURCE_TELEMETRY_GAP'
    last=now
    if row:
     row.update({'elapsedSeconds':ended-began,'sampleDurationSeconds':ended-now});telemetry.write(json.dumps(row)+'\n');telemetry.flush();samples+=1;peak=max(peak,row['rssBytes'])
     if row['rssBytes']>4<<30:stop='SAMPLED_WORKER_RSS_LIMIT'
   if sum(p.stat().st_size for p in rt.rglob('*') if p.is_file())>128<<20:stop='RUNTIME_STORAGE_LIMIT'
   if stop:break
   for key,_ in selector.select(timeout=0.1):
    data=os.read(key.fileobj.fileno(),65536)
    if not data:selector.unregister(key.fileobj);key.fileobj.close();continue
    remaining=(64<<20)-captured;files[key.data].write(data[:remaining]);captured+=min(remaining,len(data))
    if len(data)>remaining:stop='COMBINED_OUTPUT_LIMIT';break
 except BaseException as e:stop=stop or 'SUPERVISION_FAILURE_'+type(e).__name__
 finally:
  if proc is not None:
   if proc.poll() is None:
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
   proc.wait(timeout=5)
  for f in list(files.values())+([telemetry] if 'telemetry' in locals() else []):f.flush();os.fsync(f.fileno());f.close()
  for key in list(selector.get_map().values()):key.fileobj.close()
  selector.close()
  for sig,h in old.items():signal.signal(sig,h)
 after=resource.getrusage(resource.RUSAGE_CHILDREN)
 # Includes the worker AND the small owned-ps observers: conservative total.
 cpu=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
 if cpu>120:stop=stop or 'PAIR_AND_OBSERVER_CPU_LIMIT'
 result={'exitCode':proc.returncode if proc else None,'stop':stop,'wallSeconds':time.monotonic()-began,'workerAndObserverCpuSeconds':cpu,'sampledPeakWorkerRSS':peak,'samples':samples,'stdoutStderrBytes':captured,'workerReaped':proc is not None and proc.returncode is not None,'automaticRetry':False,'memoryEnforcement':'SAMPLED_RSS_NO_HARD_RESERVATION_NO_EXACT_PEAK','resourcesReliable':samples>0}
 store(rt/'PROCESS_COMPLETION.json',result);return result
def host_modules():
 def load(name,path):
  spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
 return (load('unchanged_bounded_host_capture',WS/'development/rhook-native-host-blocker-repair-01/tools/diagnostic.py'),load('unchanged_pure_host_assessor',WS/'development/rhook-near-head-canonical-actual-02/tools/run_once.py'))
def host_admission(rt):
 diagnostic,legacy=host_modules()
 capture,stdout,stderr=diagnostic.capture([str(diagnostic.NODE),str(diagnostic.OLD/'tools/host_check.mjs')],rt/'HOST_SENSOR',7)
 # capture already fsynced raw stdout/stderr and nested exitCode before evaluate.
 store(rt/'HOST_RAW.json',{'nodeCapture':capture,'stdoutFile':'HOST_SENSOR/stdout.bin','stderrFile':'HOST_SENSOR/stderr.bin'})
 decision=diagnostic.evaluate(capture,stdout,stderr,legacy.assess_host)
 accepted=decision['status']=='LEGACY_ADMISSION_PASS'
 store(rt/'HOST_ADMISSION.json',{'accepted':accepted,'recorded':decision})
 return accepted,decision,capture
def launch(path,b):
 path=Path(path);assert not path.is_symlink() and path.is_file(),'AUTHORITY_FILE'
 raw=path.read_bytes();a=authority(raw,b,time.time());rt=ROOT/'runtime'
 assert not Path(b['archivePath']).exists(),'ARCHIVE_PATH_ALREADY_USED'
 # Exclusive directory is irreversible consumption even if any later write fails.
 rt.mkdir(mode=0o700)
 d=os.open(ROOT,os.O_RDONLY)
 try:os.fsync(d)
 finally:os.close(d)
 store(rt/'FOUNDER_AUTHORIZATION.json',a)
 store(rt/'STARTED.json',{'utc':utc(),'operationCommitment':b['operationCommitment'],'authoritySha256':hashlib.sha256(raw).hexdigest(),'maximumInvocations':a['maximumInvocations'],'bothWorldsOriginalParent':True,'automaticRetry':False})
 # Keep original authority bytes for exact STARTED/binary linkage.
 with (rt/'AUTHORITY_RAW.json').open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 final={'operationCommitment':b['operationCommitment'],'terminal':'INTERRUPTED_UNVERIFIED','externalDelivery':'HOLD','economicAssurance':'UNRESOLVED','heterogeneousAgreement':'NOT_EVALUATED','automaticSuccessor':False}
 began=time.monotonic()
 try:
  # One fresh unchanged sensor/assessor window; retain nested diagnostics first.
  accepted,obj,capture=host_admission(rt)
  if not accepted:final.update({'terminal':'HOST_STOP','cause':obj.get('cause') or capture.get('captureError') or 'LEGACY_HOST_ADMISSION_FAILED','hostDecision':obj,'hostCapture':capture,'nativeInvocations':{'ACTUAL':0,'BRANCH':0,'B':0}})
  else:
   assert time.monotonic()-began<10 and time.time()+125<a['expiresUnix'],'ORIGINAL_AUTHORITY_DEADLINE'
   monitored_result=monitored(raw,rt,b['limits']);final['resources']=monitored_result
   completion=rt/'NATIVE_COMPLETION.json'
   if completion.is_file():
    n=read(completion);assert n['operationCommitment']==b['operationCommitment'];final['native']=n
    if not monitored_result['stop'] and monitored_result['resourcesReliable'] and monitored_result['workerReaped']:
     final.update(n['result'])
    else:final['cause']=monitored_result['stop'] or 'UNVERIFIED_RESOURCE_COMPLETION'
   else:final['cause']=monitored_result['stop'] or 'NATIVE_COMPLETION_MISSING'
 except BaseException as e:final['cause']=type(e).__name__+':'+str(e)[:1024]
 final.update({'RPC':0,'WSS':0,'elapsedSeconds':time.monotonic()-began,'utc':utc(),'authorityPermanentlyClosed':True})
 store(rt/'FINAL_RESULT.json',final);print(json.dumps(final));return final
def main():
 b,v=static()
 if sys.argv[1:]==['--check']:print(json.dumps(v));return
 assert len(sys.argv)==3 and sys.argv[1]=='--execute-once','EXPLICIT_FOUNDER_AUTHORITY_REQUIRED'
 launch(sys.argv[2],b)
if __name__=='__main__':main()
