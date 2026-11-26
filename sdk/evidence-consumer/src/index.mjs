import {openSync,lstatSync,fstatSync,readSync,closeSync,constants} from 'node:fs';
import {parseBytes,canonical,sha256,need,freeze,closed,isDigest,MAX_BYTES} from './codec.mjs';
import {checkBody} from './schema.mjs';

const unavailable = () => ({performed:false,accepted:false,assurance:'UNRESOLVED',profileAdmitted:false,
  comparisonEstablished:false,reason:'VERIFICATION_CONTEXT_UNAVAILABLE'});
const invalid = code => freeze({status:'INVALID',code,recordedComparison:null,reportedVerification:null,
  inspection:null,changedSubjects:[],verifiedComparison:null,verification:unavailable(),
  producerAuthenticated:false,cryptographicExecutionProof:false,canonicalFinalityEstablished:false});
const errorCode = error => typeof error?.code==='string' && /^[A-Z][A-Z0-9_]{0,63}$/.test(error.code)
  ? error.code : 'INPUT_INVALID';

/** Local integrity and recorded-value inspection only. Never grants semantic assurance. */
export function inspectEvidencePackage(input, options={}) {
  try {
    const fields=Reflect.ownKeys(Object.getOwnPropertyDescriptors(options));
    closed(options,fields,'OPTIONS_INVALID');
    need(fields.length===0 || fields.length===1 && fields[0]==='expectedSha256','OPTIONS_INVALID');
    if (fields.length) need(isDigest(options.expectedSha256),'OPTIONS_INVALID');
    const {bytes,value}=parseBytes(input),digest=sha256(bytes);
    if (fields.length) need(digest===options.expectedSha256,'TRANSPORT_PIN_MISMATCH');
    closed(value,['format','bodySha256','body']);
    need(value.format==='rhook/portable-inspection-package/0.1','PACKAGE_FORMAT_UNSUPPORTED');
    need(isDigest(value.bodySha256) && sha256(canonical(value.body))===value.bodySha256,'PACKAGE_CHECKSUM_MISMATCH');
    const checked=checkBody(value.body);
    return freeze({status:'INSPECTED',integrity:{packageChecksum:'MATCH',transportPin:fields.length?'MATCH':'NOT_SUPPLIED',packageSha256:digest},
      ...checked,verification:unavailable(),verifiedComparison:null,producerAuthenticated:false,
      cryptographicExecutionProof:false,canonicalFinalityEstablished:false});
  } catch (error) {return invalid(errorCode(error))}
}

/** Bounded regular-file reader. Packages contain inline JSON, never artifact URLs/paths. */
export function loadEvidencePackage(path, options={}) {
  let fd;
  try {
    need(typeof path==='string' && path.length>0,'FILE_UNSAFE');
    const before=lstatSync(path,{bigint:true});need(before.isFile() && !before.isSymbolicLink(),'FILE_UNSAFE');
    need(before.size<=BigInt(MAX_BYTES),'INPUT_LIMIT');
    fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
    const same=s=>s.isFile() && s.dev===before.dev && s.ino===before.ino && s.size===before.size && s.mtimeNs===before.mtimeNs;
    need(same(fstatSync(fd,{bigint:true})),'FILE_CHANGED');
    const buffer=Buffer.alloc(MAX_BYTES+1);let count=0,read;
    do {read=readSync(fd,buffer,count,buffer.length-count,null);count+=read} while(read && count<buffer.length);
    need(count<=MAX_BYTES,'INPUT_LIMIT');
    need(BigInt(count)===before.size && same(fstatSync(fd,{bigint:true})),'FILE_CHANGED');
    return inspectEvidencePackage(buffer.subarray(0,count),options);
  } catch(error) {return invalid(error.code==='INPUT_LIMIT'?'INPUT_LIMIT':error.code==='FILE_CHANGED'?'FILE_CHANGED':'FILE_UNSAFE')}
  finally {if (fd!==undefined) closeSync(fd)}
}
