import {execFileSync} from 'node:child_process';
import {need} from './common.mjs';import {checkUsage} from './pilot-policy.mjs';
// Fixed operations from the authenticated source graph, never caller-supplied argv.
const CONTROL_OPERATIONS=[
 {path:'/bin/ps',parentRoles:['owner','worker']},
 {path:'/usr/sbin/sysctl',parentRoles:['owner','coordinator','worker']},
 {path:'/usr/bin/sw_vers',parentRoles:['coordinator','worker']},
 {path:'/usr/bin/vm_stat',parentRoles:['owner','coordinator','worker']}
];
export function registeredControlOperations(files){return CONTROL_OPERATIONS.map(op=>{
 const pins=files.filter(p=>p.path===op.path);need(pins.length===1&&Number.isSafeInteger(pins[0].bytes)&&pins[0].bytes>0&&/^[0-9a-f]{64}$/.test(pins[0].sha256),'PILOT_HOST_TOOL_IDENTITY');
 return {...pins[0],parentRoles:[...op.parentRoles]};
});}
export function parseSysctl(raw,swap){
 const lines=raw.trim().split('\n');need(lines.length===2&&/^[124]$/.test(lines[0])&&/^[0-9]+$/.test(lines[1])&&Buffer.isBuffer(swap)&&swap.length===32,'PILOT_SYSCTL_ENCODING');
 const total=swap.readBigUInt64LE(0),available=swap.readBigUInt64LE(8),used=swap.readBigUInt64LE(16),page=swap.readUInt32LE(24),encrypted=swap.readUInt32LE(28);
 need(used<=total&&available<=total&&available+used===total&&used<=BigInt(Number.MAX_SAFE_INTEGER)&&[4096,16384].includes(page)&&encrypted<=1,'PILOT_SYSCTL_ENCODING');
 const physicalBytes=Number(lines[1]);need(Number.isSafeInteger(physicalBytes),'PILOT_SYSCTL_ENCODING');return {pressure:Number(lines[0]),swapUsedBytes:Number(used),physicalBytes,swapPageBytes:page};
}
export function parseVmStat(raw){
 need(typeof raw==='string','PILOT_VM_STAT_ENCODING');
 const lines=raw.split(/\r?\n/);
 need(lines.filter(s=>s.startsWith('Mach Virtual Memory Statistics:')).length===1&&lines.filter(s=>s.startsWith('Swapins:')).length===1&&lines.filter(s=>s.startsWith('Swapouts:')).length===1,'PILOT_VM_STAT_ENCODING');
 const pages=[...raw.matchAll(/^Mach Virtual Memory Statistics: \(page size of ([0-9]+) bytes\)[ \t]*$/gm)],ins=[...raw.matchAll(/^Swapins:[ \t]*([0-9]+)\.[ \t]*$/gm)],outs=[...raw.matchAll(/^Swapouts:[ \t]*([0-9]+)\.[ \t]*$/gm)];
 need(pages.length===1&&ins.length===1&&outs.length===1,'PILOT_VM_STAT_ENCODING');
 const swapPageBytes=Number(pages[0][1]),swapInPages=Number(ins[0][1]),swapOutPages=Number(outs[0][1]);
 need([4096,16384].includes(swapPageBytes)&&[swapInPages,swapOutPages].every(n=>Number.isSafeInteger(n)&&n>=0),'PILOT_VM_STAT_ENCODING');
 return {swapInPages,swapOutPages,swapPageBytes};
}
export function readDarwinHost(seq){
 need(process.platform==='darwin'&&process.arch==='arm64','PILOT_HOST_PLATFORM');
 const beganNs=process.hrtime.bigint().toString();
 const raw=execFileSync('/usr/sbin/sysctl',['-n','kern.memorystatus_vm_pressure_level','hw.memsize'],{encoding:'utf8',timeout:150,maxBuffer:4096,env:{PATH:'/usr/bin:/bin:/usr/sbin:/sbin',LANG:'C',TZ:'UTC'}});
 const swap=execFileSync('/usr/sbin/sysctl',['-bn','vm.swapusage'],{timeout:150,maxBuffer:128,env:{PATH:'/usr/bin:/bin:/usr/sbin:/sbin',LANG:'C',TZ:'UTC'}});
 const a=parseSysctl(raw,swap);
 const vm=()=>parseVmStat(execFileSync('/usr/bin/vm_stat',[],{encoding:'utf8',timeout:150,maxBuffer:8192,env:{PATH:'/usr/bin:/bin:/usr/sbin:/sbin',LANG:'C',TZ:'UTC'}}));
 const first=vm(),last=vm();
 const tail=parseSysctl(raw,execFileSync('/usr/sbin/sysctl',['-bn','vm.swapusage'],{timeout:150,maxBuffer:128,env:{PATH:'/usr/bin:/bin:/usr/sbin:/sbin',LANG:'C',TZ:'UTC'}}));
 need(a.swapPageBytes===tail.swapPageBytes&&first.swapPageBytes===a.swapPageBytes&&last.swapPageBytes===a.swapPageBytes,'PILOT_VM_STAT_ENCODING');
 const after=execFileSync('/usr/sbin/sysctl',['-n','kern.memorystatus_vm_pressure_level'],{encoding:'utf8',timeout:150,maxBuffer:128,env:{PATH:'/usr/bin:/bin:/usr/sbin:/sbin',LANG:'C',TZ:'UTC'}}).trim();
 need(/^[124]$/.test(after),'PILOT_SYSCTL_ENCODING');
 return {source:'DARWIN_SYSCTL_PRESSURE_SWAP_VM_STAT/0.2',seq,beganNs,endedNs:process.hrtime.bigint().toString(),pressureBefore:a.pressure,pressureAfter:Number(after),swapUsedBeforeBytes:a.swapUsedBytes,swapUsedBytes:tail.swapUsedBytes,swapInPagesBefore:first.swapInPages,swapInPages:last.swapInPages,swapOutPagesBefore:first.swapOutPages,swapOutPages:last.swapOutPages,swapPageBytes:a.swapPageBytes,physicalBytes:a.physicalBytes};
}
export function parsePs(text){return text.trim().split('\n').filter(Boolean).map(line=>{
 const m=/^\s*([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+(\S+\s+\S+\s+[0-9]+\s+[0-9:]+\s+[0-9]{4})\s+(.+)$/.exec(line);
 need(m,'PILOT_PS_ENCODING');const p={pid:Number(m[1]),ppid:Number(m[2]),rssBytes:Number(m[3])*1024,birth:m[4].replace(/\s+/g,' '),comm:m[5].trim()};
 need([p.pid,p.ppid,p.rssBytes].every(Number.isSafeInteger)&&p.pid>0&&p.rssBytes>=0,'PILOT_PS_ENCODING');return p;
});}
export function readProcesses(){return parsePs(execFileSync('/bin/ps',['-axo','pid=,ppid=,rss=,lstart=,comm='],{encoding:'utf8',timeout:150,maxBuffer:2000000,env:{PATH:'/usr/bin:/bin',LANG:'C',TZ:'UTC'}}));}
export class TrustedGraphScan{
 #c;#seen=new Map();#roles=new Map();
 constructor(c){this.#c={...c};}
 setWorker(pid){need(!this.#c.workerPid,'PILOT_WORKER_REPLACEMENT');this.#c.workerPid=pid;}
 check(rows,{servicePid=null,workerMayBeGone=false}={}){
  const c=this.#c,byPid=new Map(rows.map(p=>[p.pid,p]));need(byPid.size===rows.length&&byPid.has(c.ownerPid)&&byPid.has(c.coordinatorPid),'PILOT_ACCOUNTING');
  if(c.workerPid&&!workerMayBeGone)need(byPid.has(c.workerPid),'PILOT_WORKER_DISAPPEARED');
  const owned=new Set([c.ownerPid,c.coordinatorPid,...(c.workerPid?[c.workerPid]:[])]);
  let changed=true;while(changed){changed=false;for(const p of rows)if(owned.has(p.ppid)&&!owned.has(p.pid)){owned.add(p.pid);changed=true;}}
  const totals={A:0,B:0,service:0,control:0};
  for(const p of rows){
   const native=p.comm===c.A?'A':p.comm===c.B?'B':null;
   // Native executable matches outside the tree also violate exclusivity.
   if(!owned.has(p.pid)&&!native&&p.pid!==servicePid)continue;
   const prior=this.#seen.get(p.pid);if(prior)need(prior.birth===p.birth&&prior.comm===p.comm,'PILOT_PROCESS_IDENTITY');
   let role=native;
   if(p.pid===servicePid||(!role&&p.ppid===c.workerPid&&(c.serviceCommands??[]).includes(p.comm)))role='service';
   if(!role){
    const parentRole=p.ppid===c.ownerPid?'owner':p.ppid===c.coordinatorPid?'coordinator':p.ppid===c.workerPid?'worker':null;
    need([c.ownerPid,c.coordinatorPid,c.workerPid].includes(p.pid)||CONTROL_OPERATIONS.some(op=>op.path===p.comm&&op.parentRoles.includes(parentRole)),'PILOT_UNKNOWN_PROCESS');role='control';
   }
   if(native){need(owned.has(p.pid),'PILOT_FOREIGN_NATIVE_PROCESS');const old=this.#roles.get(native);need(!old||old===p.pid,'PILOT_PRODUCER_REPLACEMENT');this.#roles.set(native,p.pid);}
   if(role==='service'){const old=this.#roles.get('service');need(!old||old===p.pid,'PILOT_SERVICE_REPLACEMENT');this.#roles.set('service',p.pid);}
   this.#seen.set(p.pid,{...p,role});totals[role]+=p.rssBytes;
  }
  checkUsage(totals);return totals;
 }
 get observed(){return [...this.#seen.values()].map(p=>({...p}));}
 corroborate(rows,servicePid){
  this.check(rows,{servicePid,workerMayBeGone:true});
  need(!rows.some(p=>p.pid===this.#c.workerPid||p.pid===servicePid||p.comm===this.#c.A||p.comm===this.#c.B),'PILOT_PROCESS_REMAINS');return true;
 }
}
export function selectStopTargets(rows,observed){return observed.filter(old=>['A','B','service'].includes(old.role)&&rows.some(p=>p.pid===old.pid&&p.birth===old.birth&&p.comm===old.comm)).map(p=>p.pid);}
