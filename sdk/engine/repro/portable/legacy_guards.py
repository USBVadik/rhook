"""Exact preserved guard function bodies. Only ROOT and WS are portable context."""
from pathlib import Path
import datetime,json,os,resource,selectors,signal,subprocess,time
ROOT = None
WS = None
CHILD_ENV={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','TZ':'UTC'}

def save(path,value):
 with Path(path).open('x') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 fd=os.open(Path(path).parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)

def capture(command,directory,timeout,stdout_limit=65536,stderr_limit=65536):
 """Bound both pipes while running; keep diagnostics before interpretation."""
 directory=Path(directory);directory.mkdir()
 start=time.monotonic();proc=None;stop=None;error=None;killed=False;cleanup_error=None;sel=selectors.DefaultSelector()
 buffers={'stdout':bytearray(),'stderr':bytearray()};seen={'stdout':0,'stderr':0};truncated={'stdout':False,'stderr':False}
 def caps():
  resource.setrlimit(resource.RLIMIT_CPU,(3,3));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
  resource.setrlimit(resource.RLIMIT_FSIZE,(1<<20,1<<20));resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
 try:
  proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=CHILD_ENV,cwd=WS,start_new_session=True,preexec_fn=caps)
  save(directory/'PROCESS.json',{'pid':proc.pid,'pgid':proc.pid,'executable':str(command[0]),'argvFixedByApprovedProposal':True,'cpuSecondsPerChild':3})
  for name,stream in [('stdout',proc.stdout),('stderr',proc.stderr)]:os.set_blocking(stream.fileno(),False);sel.register(stream,selectors.EVENT_READ,name)
  while proc.poll() is None or sel.get_map():
   if time.monotonic()-start>timeout:stop='WALL_TIME_LIMIT';break
   for key,_ in sel.select(timeout=min(0.05,max(0.001,timeout-(time.monotonic()-start)))):
    chunk=os.read(key.fileobj.fileno(),8192)
    if not chunk:sel.unregister(key.fileobj);key.fileobj.close();continue
    name=key.data;seen[name]+=len(chunk);cap=stdout_limit if name=='stdout' else stderr_limit
    room=cap-len(buffers[name]);buffers[name].extend(chunk[:room])
    if len(chunk)>room:truncated[name]=True;stop='BOUNDED_'+name.upper()+'_LIMIT';break
   if stop:break
 except BaseException as e:
  stop=stop or 'CAPTURE_ERROR';error=type(e).__name__+': '+str(e)[:2048]
 finally:
  if proc is not None:
   if proc.poll() is None:
    try:os.killpg(proc.pid,signal.SIGKILL);killed=True
    except ProcessLookupError:pass
   try:proc.wait(timeout=1)
   except subprocess.TimeoutExpired:cleanup_error='OWNED_CHILD_REAP_UNCONFIRMED';stop=stop or cleanup_error
  for key in list(sel.get_map().values()):key.fileobj.close()
  sel.close()
  for name,data in buffers.items():
   with (directory/(name+'.bin')).open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 result={'command':list(map(str,command)),'exitCode':proc.returncode if proc is not None else None,'stop':stop,'captureError':error,'cleanupError':cleanup_error,'elapsedSeconds':time.monotonic()-start,'observedPipeBytes':seen,'retainedBytes':{k:len(v) for k,v in buffers.items()},'truncated':truncated,'ownedProcessGroupKilled':killed,'ownedChildReaped':proc is not None and proc.returncode is not None,'environment':'Exact three-key whitelist PATH/LANG/TZ; no inherited environment read or dump.'}
 # This record and raw buffers always precede any admission assertion.
 save(directory/'RESULT.json',result)
 return result,bytes(buffers['stdout']),bytes(buffers['stderr'])

def evaluate(result,stdout,stderr,assess):
 out={'legacyWrapperPredicate':{'returnCodeZero':result['exitCode']==0,'stderrEmpty':len(stderr)==0,'stdoutBelow65536':len(stdout)<65536},'status':'HOST_OBSERVER_OUTPUT_REJECTED'}
 if result['stop'] or any(result['truncated'].values()):out['cause']=result['stop'] or 'TRUNCATED';return out
 if result['exitCode']!=0:out['cause']='NODE_EXIT_NONZERO_OR_NOT_STARTED';return out
 if stderr:out['cause']='NODE_STDERR_NONEMPTY';return out
 if len(stdout)>=65536:out['cause']='NODE_STDOUT_EXCEEDS_LEGACY_STRICT_LIMIT';return out
 try:raw=json.loads(stdout)
 except (ValueError,UnicodeError) as e:out.update({'status':'HOST_SENSOR_JSON_REJECTED','cause':type(e).__name__});return out
 out['rawSensorPacket']=raw
 try:admission=assess(raw)
 except BaseException as e:out.update({'status':'LEGACY_ASSESSMENT_REJECTED','cause':type(e).__name__+': '+str(e)[:2048]});return out
 out.update({'status':'LEGACY_ADMISSION_PASS','admission':admission});return out

def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def store(path,value):
 with Path(path).open('x') as f:
  json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 d=os.open(Path(path).parent,os.O_RDONLY)
 try:os.fsync(d)
 finally:os.close(d)

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

def assess_host(raw):
    assert raw['bootBefore'] == raw['bootAfter'] and raw['bootAfter'], 'BOOT_CHANGED'
    samples = raw['samples']
    assert len(samples) == 2, 'SAMPLE_COUNT'
    x, y = samples
    for index, s in enumerate(samples):
        assert s['source'] == 'DARWIN_SYSCTL_PRESSURE_SWAP_VM_STAT/0.2' and s['seq'] == index
        assert s['physicalBytes'] == 25769803776 and s['swapPageBytes'] in (4096, 16384)
        assert 0 < int(s['beganNs']) <= int(s['endedNs'])
        for key in ['swapInPagesBefore', 'swapInPages', 'swapOutPagesBefore', 'swapOutPages', 'swapUsedBeforeBytes', 'swapUsedBytes']:
            assert type(s[key]) is int and 0 <= s[key] <= 9007199254740991, 'COUNTER_ENCODING'
        assert s['swapInPages'] >= s['swapInPagesBefore'] and s['swapOutPages'] >= s['swapOutPagesBefore'], 'COUNTER_REGRESSION'
    assert x['swapPageBytes'] == y['swapPageBytes'], 'PAGE_SIZE_CHANGED'
    gap = (int(y['beganNs']) - int(x['endedNs'])) / 1e9
    assert 0.9 <= gap <= 2, 'UNRELIABLE_TIMING'
    assert y['swapInPagesBefore'] >= x['swapInPages'] and y['swapOutPagesBefore'] >= x['swapOutPages'], 'COUNTER_REGRESSION'
    pressures = [s[k] for s in samples for k in ['pressureBefore', 'pressureAfter']]
    assert all(type(v) is int and v in (1, 2, 4) for v in pressures), 'PRESSURE_ENCODING'
    assert all(v == 1 for v in pressures), 'ABNORMAL_MEMORY_PRESSURE'
    outs = y['swapOutPages'] - x['swapOutPagesBefore']
    swaps = [x['swapUsedBeforeBytes'], x['swapUsedBytes'], y['swapUsedBeforeBytes'], y['swapUsedBytes']]
    assert outs == 0 and swaps == sorted(swaps, reverse=True), 'ACTIVE_SWAP_OUTPUT_OR_USAGE_GROWTH_INCONCLUSIVE'
    return {'status': 'ADMISSION_PASS', 'pressureReads': pressures, 'swapOutDeltaPages': outs,
            'swapInDeltaPages': y['swapInPages'] - x['swapInPagesBefore'], 'swapUsedBytes': y['swapUsedBytes'],
            'bootSession': raw['bootAfter'], 'reservedHeadroomEstablished': False, 'continuousHostPressureMonitoring': False}
