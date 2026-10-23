"""Pure local authentication. No application invocation, host observation or credentials."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent.parent
WS=ROOT.parents[1]
PRESERVED=[
 (WS/'development/rhook-prospective-event-observed-hookr-demo-01','b17fde213b75ee65521551eb3a50b031f4f6fa016124893d89786cfcd18f27ac','9a1a95d3ad6002b93a404f75092101cacbae8cdb6bc03cbc3f9808b54e1fd8e4',True),
 (WS/'experiments/rhook-event-observed-hookr-demo-01','f0efada08723ef86df7bca4e0a179d3b2aa26a31aa0a2f0720370bf7294da837','eac6b33363c7812975f1c0188f57892502312fb35a55508bbb1c3487982bd00f',False),
 (WS/'development/rhook-saved-hookr-block-offline-feasibility-01','880407a76b62651b844026dac27271fd45b99f590e63af575febfe102b31c832','9eb029b5dfc38dca1436ad2f0a89424d1d36d6eb0df3b0d6436e802cd57d29e2',False),
 (Path('/opt/rhook/reference/development/rhook-saved-hookr-native-pair-01'),'56e11abf0d6f530dc132317a019530010c0d9a064dba9147892d8d0f46b26ae3','4633514384e921c38eb6339e4250dde00a88be90ba8e7b0b3b5cc9b4cc07904e',True),
 (Path('/opt/rhook/reference/experiments/rhook-saved-hookr-native-pair-01'),'b2fa7608a42a6967039cd6c1ba0df45e3b600f357ba9873e92b4b8d1fe6640d7','72eea4717a6e91694dfb29c38f9ced9d7ae58aff34b28a18cb579d9cd229ff87',False),
 (Path('/opt/rhook/reference/development/rhook-native-host-blocker-repair-01'),'5623fdcef1f9c839a582261df20181f65657d1efb64087f909c70095f5545ce0','3a11392e9c6f0ac88bff372d63eb28291c402b264c0b3fe2867fe9104e2f2695',False),
 (Path('/opt/rhook/reference/experiments/rhook-native-host-preflight-01'),'d8a31938e43f28ea805e8879bbee9daa91aefde230bc1d1a143b524b68b707fd','fcd546d843887540950e2da5cf2c50ad8db9adb1190eece6efb72bfd837ee2e5',False),
]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def exact(root,manifest_pin=None,freeze_pin=None,exclude_runtime=False):
 if manifest_pin:assert sha(root/'MANIFEST.json')==manifest_pin,'MANIFEST_PIN'
 if freeze_pin:assert sha(root/'FREEZE.json')==freeze_pin,'FREEZE_PIN'
 m=read(root/'MANIFEST.json');f=read(root/'FREEZE.json')
 assert sha(root/'MANIFEST.json')==f['manifestSha256']
 wanted={'MANIFEST.json','FREEZE.json'}
 for x in m['files']:
  rel=Path(x['path']);assert not rel.is_absolute() and '..' not in rel.parts
  assert not(exclude_runtime and rel.parts[0]=='runtime')
  p=root/rel;assert not p.is_symlink() and p.stat().st_size==x['bytes'] and sha(p)==x['sha256'],str(p)
  wanted.add(rel.as_posix())
 actual=set()
 for p in root.rglob('*'):
  rel=p.relative_to(root)
  if exclude_runtime and rel.parts[0]=='runtime':continue
  assert not p.is_symlink(),str(p)
  if p.is_file():actual.add(rel.as_posix())
 assert wanted==actual,{'extra':sorted(actual-wanted),'missing':sorted(wanted-actual)}
 return {'root':str(root),'exactFiles':len(actual),'manifestSha256':sha(root/'MANIFEST.json'),'freezeSha256':sha(root/'FREEZE.json')}
def dependencies():
 m=read(ROOT/'DEPENDENCIES.json')
 for x in m['files']:
  p=Path(x['path']);assert not p.is_symlink() and p.stat().st_size==x['bytes'] and sha(p)==x['sha256'],str(p)
 return len(m['files'])
def operation_id(b):return hashlib.sha256(json.dumps({k:v for k,v in b.items() if k!='operationCommitment'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
def static():
 own=exact(ROOT,exclude_runtime=True)
 b=read(ROOT/'proposal/AUTHORIZATION_BINDINGS.json')
 assert operation_id(b)==b['operationCommitment']
 assert b.get('executionContext')=='require_escalated','EXACT_EXECUTION_CONTEXT_BINDING'
 assert sha(ROOT/'tools/run_once.py')==b['launcherSha256'],'EXACT_LAUNCHER_BINDING'
 assert sha(ROOT/'artifacts/rhook-saved-pair')==b['binarySha256']
 assert sha(ROOT/'native/plan.json')==b['planSha256']
 assert sha(ROOT/'DEPENDENCIES.json')==b['dependenciesSha256']
 assert not (ROOT/'runtime').is_symlink()
 preserved=[exact(*x) for x in PRESERVED]
 return b,{'own':own,'preserved':preserved,'dependencyFiles':dependencies(),'RPC':0,'nativeInvocations':0}
if __name__=='__main__':
 b,result=static();print(json.dumps(result,indent=2))
