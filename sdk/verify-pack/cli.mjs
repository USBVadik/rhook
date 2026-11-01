#!/usr/bin/env node
// Command-line entry for verify-pack/0.1. See README.md in this directory.
import fs from 'node:fs';
import path from 'node:path';
import {parseArgs} from 'node:util';
import {chainContextFromPackage, renderText, stableJson, verifyPackDirectory} from './verify-pack.mjs';

const USAGE = `Usage:
  node sdk/verify-pack/cli.mjs verify --bundle DIR [--pins FILE] [--trusted-block-hash 0x...] [--json] [--report FILE]
  node sdk/verify-pack/cli.mjs make-context --package BLOCK_PACKAGE.json --plan RUNTIME_PLAN.json --output CHAIN_CONTEXT.json

verify        Check a pack offline. Exit 0 when every performed check passed, 1 when a check failed.
make-context  Copy the public headers and transactions out of a local witness package after
              authenticating it. Writes a new file; never overwrites.`;

function fail(message, code = 2) {
  process.stderr.write(`${message}\n\n${USAGE}\n`);
  process.exit(code);
}

async function main(argv) {
  const [command, ...rest] = argv;
  if (command === 'verify') {
    const {values} = parseArgs({args: rest, strict: true, options: {
      bundle: {type: 'string'}, pins: {type: 'string'}, 'trusted-block-hash': {type: 'string'},
      json: {type: 'boolean', default: false}, report: {type: 'string'},
    }});
    if (!values.bundle) fail('--bundle is required');
    const report = await verifyPackDirectory(path.resolve(values.bundle), {
      pinsFile: values.pins ? path.resolve(values.pins) : null,
      trustedBlockHash: values['trusted-block-hash'] ?? null,
    });
    const json = stableJson(report);
    if (values.report) fs.writeFileSync(path.resolve(values.report), json, {flag: 'wx'});
    process.stdout.write(values.json ? json : renderText(report));
    return report.failure ? 1 : 0;
  }
  if (command === 'make-context') {
    const {values} = parseArgs({args: rest, strict: true, options: {
      package: {type: 'string'}, plan: {type: 'string'}, output: {type: 'string'},
    }});
    if (!values.package || !values.plan || !values.output) fail('--package, --plan and --output are required');
    const bytes = await chainContextFromPackage(fs.readFileSync(path.resolve(values.package)), fs.readFileSync(path.resolve(values.plan)));
    fs.writeFileSync(path.resolve(values.output), bytes, {flag: 'wx'});
    process.stdout.write(`Wrote ${path.resolve(values.output)} (${bytes.length} bytes): headers and raw transactions only.\n`);
    return 0;
  }
  fail(command ? `Unknown command ${command}` : 'A command is required');
}

main(process.argv.slice(2)).then((code) => process.exit(code), (error) => {
  process.stderr.write(`verify-pack: ${error.code ? `${error.code}: ` : ''}${error.message}\n`);
  process.exit(2);
});
