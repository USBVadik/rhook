import fs from 'node:fs';
import {inspect, plan, ruleId} from './index.ts';

function readPackage(path: string): Buffer {
  const fd = fs.openSync(path, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
  try {
    const info = fs.fstatSync(fd);
    if (!info.isFile() || info.size > 2 * 1024 * 1024) throw new Error('PACKAGE_INPUT_LIMIT');
    const data = Buffer.alloc(2 * 1024 * 1024 + 1);
    let used = 0;
    while (used < data.length) {
      const n = fs.readSync(fd, data, used, data.length - used, null);
      if (!n) break;
      used += n;
    }
    if (used > 2 * 1024 * 1024) throw new Error('PACKAGE_INPUT_LIMIT');
    return data.subarray(0, used);
  } finally {
    fs.closeSync(fd);
  }
}

try {
  const [command, flag, packagePath, ...args] = process.argv.slice(2);
  if (flag !== '--package' || !packagePath) throw new Error('USAGE');
  const input = readPackage(packagePath);
  let result;
  if (command === 'inspect' && args.length === 0) result = inspect(input);
  else if (command === 'plan' && args.length === 4 && args[0] === '--expected-old' && args[2] === '--new-value') {
    result = plan(input, {caseId: inspect(input).caseId, ruleId, expectedOld: args[1], newValue: args[3]});
  } else throw new Error('USAGE');
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  const message = error instanceof Error ? error.message : '';
  const code = /^[A-Z_]{3,64}$/.test(message) ? message : 'VALIDATION_FAILED';
  console.error(JSON.stringify({status: 'CASE_REJECTED', code}));
  process.exitCode = 1;
}
