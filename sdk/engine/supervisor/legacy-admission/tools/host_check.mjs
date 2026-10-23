// Same read-only sampler/window as the accepted Direct legacy admission.
// This file is invoked only after the separate exact founder authorization.
import {execFileSync} from 'node:child_process';
import {readDarwinHost} from '../inputs/legacy-sensor/gateway/src/pilot-host.mjs';
const boot = () => execFileSync('/usr/sbin/sysctl', ['-n', 'kern.bootsessionuuid'], {encoding:'utf8', timeout:150}).trim().toUpperCase();
const bootBefore = boot(), samples = [readDarwinHost(0)];
await new Promise(resolve => setTimeout(resolve, 1000));
samples.push(readDarwinHost(1));
console.log(JSON.stringify({bootBefore, bootAfter:boot(), samples}));
