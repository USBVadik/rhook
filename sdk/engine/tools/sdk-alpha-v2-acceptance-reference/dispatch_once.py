"""One-use outer dispatcher. No source edits, network, retries or new native authority."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,signal,subprocess,sys,time,resource
from staging import CLI_STAGING_FILE_BYTES,digest,no_links
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def store(name,v):
 with (A/name).open('x') as f:json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 fd=os.open(A,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def identities():
 rows=[]
 for path in list(W.rglob('PROCESS.json'))+list(W.rglob('PROCESS_STARTED.json')):
  try:
   v=json.loads(path.read_text());pid=v['pid'];pgid=v['pgid'];exe=v['executable']
   if type(pid) is not int or pid<=1 or pgid!=pid:continue
   if Path(exe).name not in ('rhook-host-sensor','rhook-saved-pair'):continue
   rows.append({'pid':pid,'pgid':pgid,'executable':exe,'record':str(path)})
  except (OSError,ValueError,KeyError):continue
 return {v['pid']:v for v in rows}
def observe(v):
 # Executable identity only for a PID recorded by this one operation. No resources/argv/env.
 p=subprocess.run(['/bin/ps','-p',str(v['pid']),'-o','pid=,ppid=,pgid=,comm='],capture_output=True,text=True,timeout=0.5)
 if not p.stdout.strip():return dict(v,observation='PID_ABSENT')
 lines=p.stdout.strip().splitlines()
 if len(lines)!=1:return dict(v,observation='IDENTITY_UNCONFIRMED')
 pid,ppid,pgid,exe=lines[0].strip().split(None,3)
 match=(int(pid)==v['pid'] and int(pgid)==v['pgid'] and Path(exe).name==Path(v['executable']).name)
 return dict(v,observation='OWNED_EXECUTABLE_PRESENT' if match else 'PID_IDENTITY_DIFFERENT',observedExecutable=exe,observedPPID=int(ppid))
def stop_owned():
 records=[]
 for v in identities().values():
  try:
   o=observe(v)
   if o['observation']=='OWNED_EXECUTABLE_PRESENT':
    os.killpg(v['pgid'],signal.SIGKILL);o['signal']='SIGKILL'
   records.append(o)
  except ProcessLookupError:records.append(dict(v,observation='PID_ABSENT'))
  except BaseException as e:records.append(dict(v,observation='CLEANUP_UNCONFIRMED',cause=type(e).__name__+': '+str(e)))
 return records

CLI_ENV={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','TZ':'UTC','PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1'}

def cli_caps():
 # Trusted CLI copies immutable executables (approved worker is ~124 MiB).
 # The unmodified SDK resets native worker FSIZE to 64 MiB before exec.
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 resource.setrlimit(resource.RLIMIT_FSIZE,(CLI_STAGING_FILE_BYTES,CLI_STAGING_FILE_BYTES))
 resource.setrlimit(resource.RLIMIT_NOFILE,(256,256))

def spawn_trusted_cli(command,*,cwd,stdout,stderr):
 # This exact launch path is shared by staging, acceptance and regression fixtures.
 return subprocess.Popen(command,cwd=cwd,env=CLI_ENV,stdin=subprocess.DEVNULL,
                         stdout=stdout,stderr=stderr,start_new_session=True,preexec_fn=cli_caps)

def stage_only(spec,destination):
 proc=spawn_trusted_cli([sys.executable,str(Path(__file__).with_name('staging.py')),str(spec),str(destination)],
                         cwd=Path(__file__).parent,stdout=sys.stdout,stderr=sys.stderr)
 try:return proc.wait(timeout=30)
 except BaseException:
  if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL)
  proc.wait(timeout=1)
  raise

def canonical(v):
 return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def verify_prepared_inputs(plan):
 prepared=no_links(plan['preparedInputs']);ready=json.loads(no_links(prepared/'READY.json').read_text())
 if digest(prepared/'READY.json')!=plan['preparedReadySha256']:raise ValueError('PREPARED_READY_DRIFT')
 for row in ready['inputs']:
  for p in [prepared/row['name'],Path(row['source'])]:
   if no_links(p).stat().st_size!=row['bytes'] or digest(p)!=row['sha256']:raise ValueError('STAGED_OR_ORIGINAL_INPUT_DRIFT')

def authenticate_plan(path,approval_path):
 plan=json.loads(no_links(path).read_text());approval=json.loads(no_links(approval_path).read_text())
 if canonical({k:v for k,v in plan.items() if k!='planCommitment'})!=plan['planCommitment']:raise ValueError('PLAN_COMMITMENT_DRIFT')
 if approval.get('approved') is not True or approval.get('macReady') is not True or approval.get('planCommitment')!=plan['planCommitment']:raise ValueError('FRESH_EXACT_FOUNDER_APPROVAL_REQUIRED')
 for row in plan['dispatcherFiles']:
  if digest(Path(__file__).parent/row['path'])!=row['sha256']:raise ValueError('DISPATCHER_SOURCE_DRIFT')
 # Pure file authentication, including old closed evidence and original dependencies.
 # No target code, measurement, subprocess or authority is invoked by this helper.
 from authenticate_preserved import run as authenticate_preserved
 authenticate_preserved()
 verify_prepared_inputs(plan)
 repo=Path(plan['sourceCheckout']);build=json.loads(Path(plan['buildRecord']).read_text())
 if digest(plan['buildRecord'])!=plan['buildRecordSha256']:raise ValueError('BUILD_RECORD_DRIFT')
 for rel,h in build['sourceFiles'].items():
  if digest(no_links(repo/rel))!=h:raise ValueError('SDK_SOURCE_DRIFT')
 if canonical(build['sourceFiles'])!=plan['sourceCommitment']:raise ValueError('SOURCE_CLOSURE_DRIFT')
 if canonical(json.loads((repo/'sdk_alpha_v2/policy.json').read_text()))!=plan['policySha256']:raise ValueError('POLICY_DRIFT')
 workspace=Path(plan['futureWorkspace'])
 if digest(workspace/'KIT.json')!=plan['kitConfigSha256'] or digest(workspace/'inputs/BLOCK_PACKAGE.json')!=plan['packageSha256']:raise ValueError('KIT_OR_PACKAGE_DRIFT')
 for p in [workspace/'diagnostics'/plan['futureDoctorName'],workspace/'proposals'/plan['futureRunName'],workspace/'runs'/plan['futureRunName'],Path(plan['archiveAfterOwnedWritersExit'])]:
  if p.exists() or p.is_symlink():raise ValueError('OUTPUT_OR_OPERATION_ALREADY_USED')
 return plan

def main():
 global A,PLAN,R,W
 parser=argparse.ArgumentParser(description=__doc__)
 sub=parser.add_subparsers(dest='mode',required=True)
 p=sub.add_parser('stage-only');p.add_argument('--spec',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
 p=sub.add_parser('acceptance');p.add_argument('--plan',type=Path,required=True);p.add_argument('--approval',type=Path,required=True)
 args=parser.parse_args()
 if args.mode=='stage-only':return stage_only(args.spec,args.destination)
 PLAN=authenticate_plan(args.plan,args.approval)
 A=Path(PLAN['archiveAfterOwnedWritersExit']);A.mkdir(mode=0o700)
 R=Path(PLAN['sourceCheckout']);W=Path(PLAN['futureWorkspace'])
 store('FUTURE_ACCEPTANCE_PLAN.json',PLAN)
 store('FOUNDER_APPROVAL.json',json.loads(args.approval.read_text()))
 start=time.monotonic();overall=start+180
 store('DISPATCH_STARTED.json',{'utc':utc(),'dispatcherPID':os.getpid(),'planCommitment':PLAN['planCommitment'],'policySha256':PLAN['policySha256'],'sourceCommitment':PLAN['sourceCommitment'],'workflowHardSeconds':180,'replayHardSeconds':140,'cleanupReserveSeconds':5,'deadlineEnforcement':'monotonic; SIGTERM at hard limit minus 5s; owned cleanup inside hard limit','maximumCalls':{'doctor':1,'prepare':1,'replay':1,'verify':1},'RPC':0,'WSS':0,'automaticRetry':False,'externalDelivery':'HOLD'})
 steps=[];terminal='INTERRUPTED_UNVERIFIED';cause=None;proc=None;current=None;cleanup=[]
 env={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','TZ':'UTC','PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1'}
 try:
  for spec in PLAN['steps']:
   cmd=spec['command'];name=cmd[1];current=name;began=time.monotonic();hard=min(overall,began+140) if name=='replay' else overall
   if began>=hard-5:raise RuntimeError('WORKFLOW_NO_TIME_FOR_NEXT_STAGE')
   record={'step':spec['step'],'name':name,'command':cmd,'startedUTC':utc(),'workflowElapsedAtStart':began-start,'hardLimitSeconds':hard-began,'cleanupReserveSeconds':5}
   with (A/(name+'.stdout')).open('xb') as out,(A/(name+'.stderr')).open('xb') as err:
    proc=spawn_trusted_cli(cmd,cwd=R,stdout=out,stderr=err)
    record.update({'pid':proc.pid,'pgid':proc.pid})
    store(name+'_DISPATCH.json',record)
    deadline_stop=None
    while proc.poll() is None:
     if time.monotonic()>=hard-5:
      deadline_stop='REPLAY_OUTER_TIME_LIMIT' if name=='replay' else 'WORKFLOW_OUTER_TIME_LIMIT'
      os.killpg(proc.pid,signal.SIGTERM)
      while proc.poll() is None and time.monotonic()<hard-2:time.sleep(0.02)
      cleanup.extend(stop_owned())
      if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL)
      break
     if (A/(name+'.stdout')).stat().st_size+(A/(name+'.stderr')).stat().st_size>64<<20:
      deadline_stop='CLI_OUTPUT_LIMIT';os.killpg(proc.pid,signal.SIGTERM)
      cleanup.extend(stop_owned())
      if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL)
      break
     time.sleep(0.02)
    proc.wait(timeout=max(0.001,hard-time.monotonic()))
    out.flush();os.fsync(out.fileno());err.flush();os.fsync(err.fileno())
   ended=time.monotonic();record.update({'exitCode':proc.returncode,'cliReaped':True,'elapsedSeconds':ended-began,'workflowElapsedAtEnd':ended-start,'outerStop':deadline_stop,'endedUTC':utc()})
   try:result=json.loads((A/(name+'.stdout')).read_text())
   except (ValueError,UnicodeError):result=None
   record['jsonResult']=result;steps.append(record);store(name+'_COMPLETION.json',record)
   expected=spec.get('requiredStatus',spec.get('requiredTerminal'))
   actual=result.get('terminal',result.get('status')) if isinstance(result,dict) else None
   print(json.dumps({'stage':name,'exitCode':proc.returncode,'result':actual,'elapsedSeconds':record['elapsedSeconds']}),flush=True)
   if deadline_stop:terminal='INTERRUPTED_UNVERIFIED';cause=deadline_stop;break
   if ended>hard:terminal='INTERRUPTED_UNVERIFIED';cause='OUTER_DEADLINE_EXCEEDED';break
   if proc.returncode!=0 or actual!=expected:
    terminal='HOST_STOP' if isinstance(result,dict) and (result.get('status')=='HOST_STOP' or result.get('terminal')=='HOST_STOP') else 'STOP'
    cause=name.upper()+'_FAILED';break
  else:terminal='SDK_ALPHA_V2_ACCEPTANCE_PASS'
 except BaseException as e:
  cause=type(e).__name__+': '+str(e);terminal='INTERRUPTED_UNVERIFIED'
 finally:
  if proc is not None and proc.poll() is None:
   try:os.killpg(proc.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   cleanup.extend(stop_owned())
   if proc.poll() is None:
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
   try:proc.wait(timeout=max(0.001,overall-time.monotonic()))
   except subprocess.TimeoutExpired:cause=(cause or '')+'; CLI_REAP_UNCONFIRMED';terminal='INTERRUPTED_UNVERIFIED'
  observations=[]
  for v in identities().values():
   try:observations.append(observe(v))
   except BaseException as e:observations.append(dict(v,observation='IDENTITY_UNCONFIRMED',cause=str(e)))
  writers_gone=all(o['observation'] in ('PID_ABSENT','PID_IDENTITY_DIFFERENT') for o in observations)
  if not writers_gone:terminal='INTERRUPTED_UNVERIFIED';cause=(cause or '')+'; OWNED_WRITER_EXIT_UNCONFIRMED'
  elapsed=time.monotonic()-start
  if elapsed>180:terminal='INTERRUPTED_UNVERIFIED';cause=(cause or '')+'; WORKFLOW_180S_EXCEEDED'
  store('OWNED_WRITER_EXIT_OBSERVATION.json',{'observations':observations,'allRecordedOwnedWriterExecutablesAbsent':writers_gone,'cleanup':cleanup,'cliProcessesReaped':all(r.get('cliReaped') for r in steps),'noArgvEnvResourceMeasurements':True})
  final={'terminal':terminal,'cause':cause,'lastStage':current,'completedStages':len(steps),'workflowElapsedSeconds':elapsed,'workflowLimitSeconds':180,'replayLimitSeconds':140,'allRecordedOwnedWritersExited':writers_gone,'steps':steps,'endedUTC':utc(),'automaticRetry':False,'RPC':0,'WSS':0,'externalDelivery':'HOLD'}
  store('WORKFLOW_RESULT.json',final)
  print(json.dumps({'terminal':terminal,'cause':cause,'workflowElapsedSeconds':elapsed,'archive':str(A)}),flush=True)
 return 0 if terminal=='SDK_ALPHA_V2_ACCEPTANCE_PASS' else 1

if __name__=='__main__':
 sys.exit(main())
