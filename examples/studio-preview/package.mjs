import {mkdir,writeFile,readFile,lstat} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {PUBLIC_FILES} from './public-files.mjs';
const output = process.argv[2];
if (!output) throw Error('Usage: node examples/studio-preview/package.mjs NEW_OUTPUT_DIRECTORY');
const dest=resolve(output);
// Exclusive creation prevents accidental overwrite of an existing deployment or checkout.
await mkdir(dest,{recursive:false});
const files={};
for(const name of PUBLIC_FILES){
  const source=new URL('./'+name,import.meta.url);
  if(!(await lstat(source)).isFile())throw Error('Package source must be a regular file: '+name);
  const bytes=await readFile(source);await mkdir(dirname(resolve(dest,name)),{recursive:true});await writeFile(resolve(dest,name),bytes,{flag:'wx'});
  files[name]=createHash('sha256').update(bytes).digest('hex');
}
console.log(JSON.stringify({status:'STATIC_PACKAGE_READY',files,publicationPerformed:false,deploymentPerformed:false},null,2));
