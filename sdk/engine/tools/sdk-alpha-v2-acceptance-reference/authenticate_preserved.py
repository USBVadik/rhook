"""Read-only authentication; no target imports, sensor calls or worker execution."""
from pathlib import Path
import hashlib,json
ROOT=Path('/opt/rhook/reference')
HERE=Path(__file__).resolve().parent

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def canonical(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def authenticate(path,m,f):
 assert digest(path/'MANIFEST.json')==m and digest(path/'FREEZE.json')==f,path
 manifest=read(path/'MANIFEST.json');rows=manifest['files']
 if isinstance(rows,dict):rows=[dict(path=k,**v) for k,v in rows.items()]
 expected={'MANIFEST.json','FREEZE.json'}
 for row in rows:
  q=path/row['path'];assert q.is_file() and not q.is_symlink() and digest(q)==row['sha256'],q
  assert q.stat().st_size==row['bytes'];expected.add(row['path'])
 actual={str(q.relative_to(path)) for q in path.rglob('*') if q.is_file()}
 assert actual==expected
 return {'path':str(path),'manifestSha256':m,'freezeSha256':f,'exactFiles':len(actual),'status':'PASS'}
def run():
 old=ROOT/'experiments/rhook-developer-memory-v2-sdk-acceptance-01'
 checked=[authenticate(old,'023c56ef9b481c1b9f75c314063b6b2baeb715e6165dc6b97951552798e1a1c8','63a2971a1f42680d2cd3ea73f03344573445ab5f86ed07e57b43d884d76ac3c6')]
 for row in read(old/'PRELAUNCH_AUTHENTICATION.json')['archives']:
  checked.append(authenticate(Path(row['path']),row['manifestSha256'],row['freezeSha256']))
 P=ROOT/'development/rhook-developer-memory-profile-v2-preparation-01';plan=read(P/'FUTURE_ACCEPTANCE_PLAN.json');R=Path(plan['sourceCheckout']);v=read(P/'SOURCE_AND_BUILD_VALIDATION.json')
 for row in v['baseFilesByteIdentical']+v['newFiles']:
  q=R/row['path'];assert digest(q)==row['sha256'] and q.stat().st_size==row['bytes']
  if 'mode' in row:assert bool(q.stat().st_mode&0o111)==(row['mode']=='100755')
 build=read(plan['buildRecord']);assert digest(plan['buildRecord'])==plan['buildRecordSha256']
 for rel,h in build['sourceFiles'].items():assert digest(R/rel)==h
 for row in build['goDependencyFiles']:assert digest(Path('/private/tmp/rhook-pair03-cleanroom-build-01')/row['path'])==row['sha256']
 assert canonical(build['sourceFiles'])==plan['sourceCommitment']
 assert digest(build['worker'])==plan['workerSha256'] and digest(build['sensor'])==plan['sensorSha256']
 assert canonical(read(R/'sdk_alpha_v2/policy.json'))==plan['policySha256']
 stage=HERE/'prepared-inputs';ready=read(stage/'READY.json');assert ready['status']=='INPUTS_STAGED_NOT_AUTHORIZED_NOT_EXECUTED'
 for row in ready['inputs']:
  for q in [stage/row['name'],Path(row['source'])]:assert digest(q)==row['sha256'] and q.stat().st_size==row['bytes']
 return {'status':'PRESERVED_AND_STAGED_INPUTS_AUTHENTICATED','archives':checked,'baseFilesUnchanged':len(v['baseFilesByteIdentical']),'v2FilesUnchanged':len(v['newFiles']),'buildDependencyFilesUnchanged':len(build['goDependencyFiles']),'sourceCommitment':plan['sourceCommitment'],'policySha256':plan['policySha256'],'workerSha256':plan['workerSha256'],'stagedWorkerBytes':(stage/'rhook-saved-pair').stat().st_size,'sensorSha256':plan['sensorSha256'],'packageSha256':plan['packageSha256'],'newDoctorCalls':0,'historicalEVM':0,'RPC':0,'WSS':0,'scientificAuthorities':0,'externalDelivery':'HOLD'}
if __name__=='__main__':
 result=run()
 with (HERE/'PRESERVED_AUTHENTICATION.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps({k:v for k,v in result.items() if k!='archives'},indent=2))
