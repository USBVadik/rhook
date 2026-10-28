"""Build a separate offline scenario worker using the retained Nitro toolchain."""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
SDK=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(SDK))
from developer.files import canonical,digest,no_links,require,save,sha


def build(retained,output,sensor,node):
    retained=no_links(retained);output=no_links(output)
    require(not output.exists() and not output.is_relative_to(SDK),'FRESH_EXTERNAL_BUILD_REQUIRED')
    output.mkdir(mode=0o700)
    shutil.copytree(retained/'application/prestate',output/'prestate')
    module=output/'scenario';module.mkdir()
    sources=SDK/'rhook_alpha/cases/scenario/native'
    for p in sources.iterdir():
        if p.suffix=='.go' or p.name=='profile.json':
            shutil.copyfile(p,(output/'prestate' if p.name=='scenario_setup.go' else module)/p.name)
    (module/'cmd').mkdir()
    (module/'cmd/main.go').write_text('package main\nimport("fmt";"os";scenario "local/rhook-scenario")\nvar sourceCommitment,policyCommitment string\nfunc main(){if e:=scenario.WorkerEntry(sourceCommitment,policyCommitment,os.Args[1:]);e!=nil{fmt.Fprintln(os.Stderr,e);os.Exit(1)}}\n')
    for folder,original,name in [(output/'prestate',retained/'application/prestate','local/rhook-robinhood'),(module,retained/'application/worker','local/rhook-scenario')]:
        text=(original/'go.mod').read_text();text=re.sub(r'(?m)^module .*$', 'module '+name,text,count=1)
        for dependency,target in {'github.com/ethereum/go-ethereum':retained/'src/nitro/go-ethereum','github.com/offchainlabs/nitro':retained/'src/nitro','local/rhook-robinhood':output/'prestate'}.items():
            text=re.sub(r'(?m)^(replace '+re.escape(dependency)+r' => )[^\n]+',lambda m:m[1]+os.path.relpath(target,folder),text)
        (folder/'go.mod').write_text(text);shutil.copyfile(original/'go.sum',folder/'go.sum')
    files={str(p.relative_to(output)):sha(p) for folder in ['prestate','scenario'] for p in sorted((output/folder).rglob('*')) if p.is_file()}
    identity=digest(canonical(files));policy=sha(SDK/'rhook_alpha/cases/scenario/policy.json');go=retained/'go/bin/go'
    env={'PATH':str(go.parent)+':/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(output),'GOENV':'off','GOWORK':'off','GOTOOLCHAIN':'local','GOPROXY':'off','GOSUMDB':'off','GOMODCACHE':str(retained/'go-mod'),'GOCACHE':str(retained/'go-cache-clean'),'GOMAXPROCS':'2','GOMEMLIMIT':'536870912','CGO_ENABLED':'1','CGO_LDFLAGS':'-Wl,-no_warn_duplicate_libraries','LANG':'C','TZ':'UTC'}
    def caps():
        resource.setrlimit(resource.RLIMIT_CPU,(300,300));resource.setrlimit(resource.RLIMIT_FSIZE,(256<<20,256<<20));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    ld='-s -w -X main.sourceCommitment='+identity+' -X main.policyCommitment='+policy
    for name,args in [('tests',['test','-mod=readonly','-count=1','-p','2','-v','.']),('graph',['list','-mod=readonly','-deps','-json','./cmd']),('build',['build','-mod=readonly','-trimpath','-p','2','-ldflags='+ld,'-o',str(output/'worker.bin'),'./cmd'])]:
        with (output/(name+'.log')).open('xb') as log:
            child=subprocess.Popen([str(go),*args],cwd=module,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=caps)
            try:code=child.wait(timeout=600)
            finally:
                if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
        require(code==0,'BUILD_STAGE_FAILED: '+name)
    compiled={};text=(output/'graph.log').read_text();decoder=json.JSONDecoder()
    while text.strip():
        row,end=decoder.raw_decode(text.lstrip());text=text.lstrip()[end:]
        require(not row.get('Error') and not row.get('DepsErrors'),'COMPILER_DEPENDENCY_ERROR')
        for key in ['GoFiles','CgoFiles','CFiles','CXXFiles','MFiles','HFiles','FFiles','SFiles','SysoFiles','EmbedFiles']:
            for name in row.get(key,[]):p=Path(row['Dir'])/name;compiled[str(p)]=sha(p)
    require(files=={str(p.relative_to(output)):sha(p) for folder in ['prestate','scenario'] for p in sorted((output/folder).rglob('*')) if p.is_file()},'BUILD_SOURCE_DRIFT')
    save(output/'BUILD.json',{'schema':'rhook/scenario-worker-build/0.1','sourceCommitment':identity,'sourceFiles':files,'compiledFiles':compiled,'binarySha256':sha(output/'worker.bin'),'toolchainSha256':sha(go),'policySha256':policy,'nativeExecutions':0,'limitations':'Direct compiler inputs/embeds; indirect C/assembly include closure is not exhaustive'})
    runtime={'schema':'rhook/scenario-runtime/0.1','profile':'nitro-hookr-scenario/0.1','sourceCommitment':identity,'policySha256':policy,'files':{name:{'path':str(no_links(path)),'sha256':sha(path)} for name,path in [('worker',output/'worker.bin'),('sensor',sensor),('node',node)]}}
    save(output/'RUNTIME.json',runtime)
    return {'status':'BUILD_ONLY_PASS','sourceCommitment':identity,'binarySha256':sha(output/'worker.bin'),'runtime':str(output/'RUNTIME.json'),'nativeExecutions':0}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['retained','output','sensor','node']:parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();print(json.dumps(build(a.retained,a.output,a.sensor,a.node)))
