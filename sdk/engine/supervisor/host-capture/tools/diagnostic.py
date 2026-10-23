"""One approved host-only preflight. Default/check performs no host observation."""
from pathlib import Path
import datetime,hashlib,importlib.util,json,os,resource,selectors,signal,subprocess,sys,time
ROOT=Path(__file__).resolve().parent.parent
WS=ROOT.parents[1]
CHILD_ENV={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','TZ':'UTC'}
NODE=Path('/opt/rhook/runtime/node')
OLD=WS/'development/rhook-near-head-canonical-actual-02'
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
 return h.hexdigest()
def read(path):return json.loads(Path(path).read_text())
def save(path,value):
 with Path(path).open('x') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 fd=os.open(Path(path).parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def op_id(b):return hashlib.sha256(json.dumps({k:v for k,v in b.items() if k!='operationCommitment'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
def verify():
 freeze=read(ROOT/'FREEZE.json');assert sha(ROOT/'MANIFEST.json')==freeze['manifestSha256']
 manifest=read(ROOT/'MANIFEST.json');want={'MANIFEST.json','FREEZE.json'}
 for x in manifest['files']:
  rel=Path(x['path']);assert not rel.is_absolute() and '..' not in rel.parts
  p=ROOT/rel;assert not p.is_symlink() and p.stat().st_size==x['bytes'] and sha(p)==x['sha256'],str(p)
  want.add(rel.as_posix())
 assert want=={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()},'EXACT_PREPARATION_SET'
 b=read(ROOT/'proposal/AUTHORIZATION_BINDINGS.json');assert b['operationCommitment']==op_id(b)
 assert sha(ROOT/'tools/diagnostic.py')==b['scriptSha256'],'DIAGNOSTIC_SOURCE_BINDING'
 for x in b['externalPins']:
  p=Path(x['path']);assert not p.is_symlink() and p.stat().st_size==x['bytes'] and sha(p)==x['sha256'],str(p)
 return b
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
def permit(raw,b,now):
 assert len(raw)<8192
 a=json.loads(raw)
 assert a.get('founderApproved') is True and a.get('domain')=='HOST_DIAGNOSTIC_PREFLIGHT_ONLY','HOST_ONLY_FOUNDER_APPROVAL_REQUIRED'
 assert a.get('operationCommitment')==b['operationCommitment'] and a.get('executionContext')=='require_escalated','EXACT_CONTEXT_APPROVAL_REQUIRED'
 assert a.get('ACTUAL')==a.get('BRANCH')==a.get('B')==a.get('RPC')==a.get('WSS')==0,'HOST_ONLY_SCOPE'
 assert a.get('hostNodeInvocations')==1 and a.get('ownProcessQueries')==1 and a.get('outputPath')==b['outputPath'],'EXACT_SINGLE_PREFLIGHT'
 assert a.get('notBeforeUnix',now+1)<=now and a.get('expiresUnix',0)-now>=15 and a['expiresUnix']-a['notBeforeUnix']<=300,'PERMIT_WINDOW'
 return a
def main():
 b=verify()
 if sys.argv[1:]==['--check']:print(json.dumps({'status':'HOST_PREFLIGHT_PREPARED_NOT_AUTHORIZED','operationCommitment':b['operationCommitment'],'realHostSensors':0,'nativeInvocations':0}));return
 assert len(sys.argv)==3 and sys.argv[1]=='--preflight-once','EXACT_HOST_ONLY_APPROVAL_REQUIRED'
 raw=Path(sys.argv[2]).read_bytes();a=permit(raw,b,time.time());out=Path(b['outputPath']);out.mkdir(mode=0o700)
 fd=os.open(out.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 save(out/'PERMIT.json',a);save(out/'STARTED.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'operationCommitment':b['operationCommitment'],'permitRawSha256':hashlib.sha256(raw).hexdigest(),'scientificAuthorityConsumed':False,'singleHostDiagnosticPermitConsumed':True})
 with (out/'PERMIT_RAW.json').open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 # Known self PID avoids unrelated process exposure and remains alive even if
 # the Node sensor immediately exits. This is a capability check, not a gate
 # that prevents collecting the one independently authorized Node diagnostic.
 process,psout,pserr=capture(['/bin/ps','-p',str(os.getpid()),'-o','pid=,ppid=,pgid=,rss=,comm='],out/'OWN_PROCESS',1,8192,8192)
 if process['cleanupError']:
  save(out/'FINAL_RESULT.json',{'status':'HOST_DIAGNOSTIC_CLEANUP_UNVERIFIED','ACTUAL':0,'BRANCH':0,'B':0,'RPC':0,'WSS':0,'scientificAuthorityConsumed':False,'hostOnlyPermitPermanentlyClosed':True});return
 fields=psout.decode(errors='replace').strip().split(None,4)
 process_ok=not process['stop'] and process['exitCode']==0 and not pserr and len(fields)==5 and fields[0]==str(os.getpid())
 node,stdout,stderr=capture([str(NODE),str(OLD/'tools/host_check.mjs')],out/'NODE_SENSOR',7)
 module_path=OLD/'tools/run_once.py';spec=importlib.util.spec_from_file_location('pinned_pure_legacy_assessor',module_path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 result=evaluate(node,stdout,stderr,module.assess_host)
 result.update({'operationCommitment':b['operationCommitment'],'ownProcessVisibilityPassed':process_ok,'scientificAuthorityConsumed':False,'ACTUAL':0,'BRANCH':0,'B':0,'RPC':0,'WSS':0,'externalDelivery':'HOLD','automaticRetry':False,'automaticSuccessor':False,'hostOnlyPermitPermanentlyClosed':True})
 if result['status']=='LEGACY_ADMISSION_PASS':result['readiness']='LEGACY_GATE_COMPATIBLE_WITH_EXPLICIT_CONTEXT' if process_ok else 'NATIVE_PROCESS_OBSERVER_CONTEXT_NOT_READY'
 else:result['readiness']='HOST_BLOCKER_RECORDED_NO_NATIVE_AUTHORIZATION'
 save(out/'FINAL_RESULT.json',result);print(json.dumps({'status':result['status'],'readiness':result['readiness'],'output':str(out),'nativeInvocations':0}))
if __name__=='__main__':main()
