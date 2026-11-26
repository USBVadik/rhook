// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import path from 'node:path';
import {fail, need, sha256} from '../codec.mjs';
import {parseStrictEvidenceJson} from '../../vendor/strict-json.mjs';

export const blockHash = /^0x[0-9a-f]{64}$/;

export function localRoot(input) {
  need(typeof input === 'string' && input.length > 0, 'EVIDENCE_ROOT_REQUIRED');
  const root = path.resolve(input);
  need(fs.realpathSync(root) === root && fs.statSync(root).isDirectory(), 'EVIDENCE_PATH_UNSAFE');
  return root;
}

export function readPinned(root, name, pin) {
  need(typeof name === 'string' && name.split('/').every(part => /^[\w.-]+$/.test(part) &&
    part !== '.' && part !== '..') && pin, 'EVIDENCE_REF_UNKNOWN');
  const file = path.join(root, name);
  // Read only an allowlisted regular file, without following symlinks in the selected tree.
  let current = root;
  for (const part of name.split('/')) {
    current = path.join(current, part);
    need(!fs.lstatSync(current).isSymbolicLink(), 'EVIDENCE_PATH_UNSAFE');
  }
  need(fs.realpathSync(file) === file, 'EVIDENCE_PATH_UNSAFE');
  const bytes = readRegularBytes(file, pin.bytes, pin.bytes);
  need(sha256(bytes) === pin.sha256, 'EVIDENCE_HASH_MISMATCH');
  return bytes;
}

export function readRegularBytes(file, maxBytes, exactBytes) {
  const fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
  try {
    const original = fs.fstatSync(fd, {bigint: true});
    need(original.isFile(), 'EVIDENCE_PATH_UNSAFE');
    need(original.size <= BigInt(maxBytes) &&
      (exactBytes === undefined || original.size === BigInt(exactBytes)), 'EVIDENCE_SIZE_MISMATCH');
    const bytes = Buffer.alloc(Number(original.size));
    let offset = 0;
    while (offset < bytes.length) {
      const count = fs.readSync(fd, bytes, offset, bytes.length - offset, null);
      need(count > 0, 'EVIDENCE_CHANGED');
      offset += count;
    }
    const final = fs.fstatSync(fd, {bigint: true});
    need(original.size === final.size && original.mtimeNs === final.mtimeNs &&
      original.ctimeNs === final.ctimeNs, 'EVIDENCE_CHANGED');
    return bytes;
  } finally {
    fs.closeSync(fd);
  }
}

export function parseEvidence(bytes) {
  // Inputs already match an external byte pin, or bounded output of an admitted verifier.
  // Keep the native JSON shape. The 4 MiB canonical wire codec is for Branch Protocol objects.
  return parseStrictEvidenceJson(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
}

export function evidenceRef(name, pin) {
  if (!pin) fail('EVIDENCE_REF_UNKNOWN');
  return Object.freeze({name, size: pin.bytes, sha256: pin.sha256});
}

export function checkLink(condition) {
  need(condition, 'CASE_CROSSLINK_MISMATCH');
}
