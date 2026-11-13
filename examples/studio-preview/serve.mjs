import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {PUBLIC_FILES} from './public-files.mjs';
const types = {html:'text/html; charset=utf-8',mjs:'text/javascript; charset=utf-8',css:'text/css; charset=utf-8',json:'application/json',md:'text/plain; charset=utf-8',txt:'text/plain; charset=utf-8'};
export function createPreviewServer() {
  return createServer(async (req,res) => {
    const name = new URL(req.url, 'http://preview.invalid').pathname.slice(1) || 'index.html';
    res.setHeader('Cache-Control','no-store'); res.setHeader('X-Content-Type-Options','nosniff'); res.setHeader('Referrer-Policy','no-referrer');
    if (!['GET','HEAD'].includes(req.method)) {res.writeHead(405);res.end();return;}
    if (!PUBLIC_FILES.includes(name)) {res.writeHead(404);res.end();return;}
    try {const body = await readFile(new URL('./'+name,import.meta.url));res.writeHead(200,{'Content-Type':types[name.split('.').at(-1)] ?? 'text/plain','Content-Length':body.length});res.end(req.method === 'HEAD' ? undefined : body);}
    catch {res.writeHead(404);res.end();}
  });
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port=Number(process.env.PORT ?? 4173);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw Error('PORT must be 1024–65535.');
  const server=createPreviewServer();server.listen(port,'127.0.0.1',()=>console.log('Local: http://127.0.0.1:'+port));
  for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>server.close(()=>process.exit(0)));
}
