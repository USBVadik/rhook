"""Build/test the historical derivative from retained offline dependencies only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from developer.files import canonical, digest, load, read, require, sha
from . import PROFILE
from .stage import compose

SDK=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent


def build(retained, output, reference, fixture=None):
    retained=Path(retained).resolve();out=Path(output).absolute()
    require(not out.exists(),'FRESH_BUILD_DIRECTORY_REQUIRED')
    go=retained/'go/bin/go';lib=retained/'src/nitro/target/lib/libstylus.a'
    reference=load(reference,8<<20)
    require(sha(go)==reference['toolchainSha256'],'RETAINED_GO_TOOLCHAIN_PIN')
    for n,pin in reference['compilerFiles'].items():
        if Path(n).is_relative_to(retained): require(sha(n,512<<20)==pin,'RETAINED_COMPILER_SOURCE_DRIFT: '+n)
    require(sha(lib,512<<20)=='d9b05f1e0d3937fd155f194c2b0c610e8966cc1b2f2c449912b21a39d2615b55','LIBSTYLUS_PIN')
    out.mkdir(mode=0o700);pre=out/'prestate';worker=out/'worker';worker.mkdir()
    shutil.copytree(SDK/'engine/native/prestate',pre)
    for p in pre.glob('*_test.go'): p.unlink() # no historical producer tests are dispatched
    (pre/'historical_dynamic.go').write_bytes(read(HERE/'overlay.go'))
    (pre/'historical_dynamic_test.go').write_bytes(read(HERE/'overlay_test.go'))
    compose(SDK,pre,worker)
    shutil.copyfile(HERE/'worker_extra_test.go',worker/'historical_extra_test.go')
    shutil.copyfile(SDK/'engine/native/saved-pair/go.sum',worker/'go.sum')
    mods={ 'github.com/ethereum/go-ethereum':retained/'src/nitro/go-ethereum', 'github.com/offchainlabs/nitro':retained/'src/nitro', 'local/rhook-robinhood':pre}
    for src,dest in [(SDK/'engine/native/prestate',pre),(SDK/'engine/native/saved-pair',worker)]:
        text=(src/'go.mod').read_text()
        for module,target in mods.items():
            if module=='local/rhook-robinhood' and dest==pre: continue
            text,n=re.subn(r'(?m)^replace '+re.escape(module)+r' => [^\n]+',lambda _: 'replace '+module+' => '+os.path.relpath(target,dest),text)
            require(n==1,'MODULE_REPLACEMENT_COUNT')
        (dest/'go.mod').write_text(text)
    env=os.environ.copy();env.update(GOROOT=str(retained/'go'),GOPROXY='off',GOSUMDB='off',GOWORK='off',GOTOOLCHAIN='local',GOENV='off',GOCACHE=str(retained/'go-cache'),GOMODCACHE=str(retained/'go-mod'),GOMAXPROCS='2',CGO_ENABLED='1')
    if fixture:env['RHOOK_HISTORICAL_TEST_PACKAGE']=str(Path(fixture).resolve())
    def run(label,args,cwd=worker):
        with (out/(label+'.log')).open('xb') as f:subprocess.run(args,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
    run('gofmt',[str(retained/'go/bin/gofmt'),'-w',str(pre/'runner.go'),str(pre/'historical_dynamic.go'),str(pre/'historical_dynamic_test.go'),*[str(worker/n) for n in ['main.go','pair.go','main_test.go','pair_test.go']]])
    run('overlay-tests',[str(go),'test','-p','1','-count=1','-v','-run','^TestHistorical', '.'],pre)
    run('worker-tests',[str(go),'test','-p','1','-count=1','-v','.'])
    run('graph',[str(go),'list','-mod=readonly','-deps','-json','.'])
    text=(out/'graph.log').read_text();dec=json.JSONDecoder();files={}
    while text.strip():
        row,end=dec.raw_decode(text.lstrip());text=text.lstrip()[end:];require(not row.get('Error') and not row.get('DepsErrors'),'COMPILER_GRAPH')
        for field in ['GoFiles','CgoFiles','CFiles','CXXFiles','MFiles','HFiles','FFiles','SFiles','SysoFiles','EmbedFiles']:
            for n in row.get(field,[]):
                p=(Path(row['Dir'])/n).resolve();require(p.is_relative_to(retained) or p.is_relative_to(out),'UNRETAINED_COMPILER_INPUT');files[str(p)]=sha(p,512<<20)
                if p.is_relative_to(retained): require(reference['compilerFiles'].get(str(p))==files[str(p)],'UNAUTHENTICATED_RETAINED_INPUT: '+str(p))
    policy=sha(HERE/'policy.json')
    body=dict(profile=PROFILE,compilerFiles=files,policySha256=policy,toolchainSha256=sha(go),libstylusSha256=sha(lib,512<<20),options=dict(trimpath=True,s=True,w=True,GOPROXY='off',GOSUMDB='off'))
    identity=digest(b'rhook/historical-dynamic-build/0.1\n'+canonical(body))
    run('build',[str(go),'build','-p','1','-trimpath','-ldflags',f'-s -w -X main.sourceCommitment={identity} -X main.policyCommitment={policy}','-o',str(out/'worker.bin'),'.'])
    require((out/'worker.bin').stat().st_size<=64<<20,'WORKFLOW_FILE_LIMIT_64MIB')
    require(all(sha(p,512<<20)==pin for p,pin in files.items()),'COMPILER_INPUT_CHANGED')
    result=dict(body,status='OFFLINE_BUILD_PASS',sourceCommitment=identity,binarySha256=sha(out/'worker.bin'),workerBytes=(out/'worker.bin').stat().st_size,nativeProducerInvocations=0)
    (out/'BUILD.json').write_bytes(canonical(result)+b'\n')
    print(json.dumps({k:result[k] for k in ['status','profile','sourceCommitment','binarySha256','workerBytes','nativeProducerInvocations']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--retained',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reference-build',type=Path,required=True);p.add_argument('--fixture',type=Path)
    a=p.parse_args();build(a.retained,a.output,a.reference_build,a.fixture)
