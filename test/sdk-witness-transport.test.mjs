import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { createTransport } from "../sdk/rhook_alpha/cases/witness/transport.mjs";
function mock({ body = Buffer.from("{}"), headers = {}, status = 200, hang = false, complete = true, rawHeaders = [], rawTrailers = [], reusedSocket = false } = {}) {
  let writes = 0, destroyed = 0, options;
  const socket = Object.assign(new EventEmitter(), {authorized:true,remoteAddress:"192.0.2.1",remotePort:443});
  const agent = { destroy: () => destroyed++ };
  const request = (url, opts, callback) => {
    options = { url, ...opts };
    const req = new EventEmitter();
    req.reusedSocket=reusedSocket;
    req.destroy = () => {
    };
    req.end = () => {
      writes++;
      if (hang) return;
      queueMicrotask(() => {
        req.emit("socket",socket);
        const res = new PassThrough();
        Object.assign(res, { statusCode: status, headers, rawHeaders, rawTrailers, complete });
        callback(res);
        res.end(body);
      });
    };
    return req;
  };
  const t = createTransport({ endpoint: "https://rpc.mainnet.chain.robinhood.com", request, agent });
  return { t, counts: () => ({ writes, destroyed, options, socket }) };
}
const ctx = () => ({ deadline: process.hrtime.bigint() + 500000000n, maxBody: 65536, maxHeader: 8192, maxResponse: 1048576 });
test("bounded stream preserves bytes and forces exact TLS destination", async () => {
  const m = mock({ body: Buffer.from('{"hello":1}'), rawHeaders: ["X-Backend", "test"] });
  const r = await m.t.send(Buffer.from("{}"), ctx());
  m.t.close();
  assert.equal(r.body.toString(), '{"hello":1}');
  assert.equal(r.failure, void 0);
  assert.equal(m.counts().writes, 1);
  assert.equal(m.counts().destroyed, 1);
  assert.equal(m.counts().options.url, "https://rpc.mainnet.chain.robinhood.com");
  assert.equal(m.counts().options.rejectUnauthorized, true);
});
test("oversized chunk is not consumed beyond application cap", async () => {
  const m = mock({ body: Buffer.alloc(65537) });
  const r = await m.t.send(Buffer.from("{}"), ctx());
  m.t.close();
  assert.equal(r.failure, "BODY_LIMIT");
  assert.equal(r.body.length, 65536);
  assert.equal(m.counts().writes, 1);
});
test("exact body cap may end successfully", async () => {
  const m = mock({ body: Buffer.alloc(65536) });
  const r = await m.t.send(Buffer.from("{}"), ctx());
  m.t.close();
  assert.equal(r.failure, void 0);
  assert.equal(r.body.length, 65536);
});
test("headers count toward combined cap; preserve bounded rejected prefix", async () => {
  const m = mock({ rawHeaders: ["X-Header", "a".repeat(8192)] });
  const r = await m.t.send(Buffer.from("{}"), ctx());
  m.t.close();
  assert.equal(r.failure, "HEADER_LIMIT");
  assert.equal(r.headers.length, 8192);
});
test("combined remaining cap applies before reading body", async () => {
  const m = mock({ body: Buffer.alloc(10), rawHeaders: [] });
  const r = await m.t.send(Buffer.from("{}"), { ...ctx(), maxResponse: 34 });
  m.t.close();
  assert.equal(r.failure, "BODY_LIMIT");
  assert.equal(r.body.length + r.headers.length, 34);
});
test("unexpected compression rejected without decoding", async () => {
  const m = mock({ headers: { "content-encoding": "gzip" } });
  const r = await m.t.send(Buffer.from("{}"), ctx());
  m.t.close();
  assert.equal(r.failure, "UNEXPECTED_ENCODING");
  assert.equal(r.body.length, 0);
});
test("oversized content length stops before consuming body", async () => {
  const m = mock({ headers: { "content-length": "999999" } });
  const r = await m.t.send(Buffer.from("{}"), ctx());
  m.t.close();
  assert.equal(r.failure, "BODY_LIMIT");
  assert.equal(r.body.length, 0);
});
test("hang times out once, without retry", async () => {
  const m = mock({ hang: true });
  const r = await m.t.send(Buffer.from("{}"), { ...ctx(), deadline: process.hrtime.bigint() + 10000000n });
  m.t.close();
  assert.equal(r.failure, "REQUEST_TIMEOUT");
  assert.equal(m.counts().writes, 1);
});
test("cancellation destroys owned request", async () => {
  const m = mock({ hang: true }), a = new AbortController();
  const promise = m.t.send(Buffer.from("{}"), { ...ctx(), signal: a.signal });
  a.abort();
  const r = await promise;
  m.t.close();
  assert.equal(r.failure, "CANCELLED");
  assert.equal(m.counts().writes, 1);
});
test("closed transport cannot send", async () => {
  const m = mock();
  m.t.close();
  await m.t.send(Buffer.from("{}"), ctx());
  assert.equal(m.counts().writes, 0);
});
test("incomplete HTTP response stops", async () => {
  const m = mock({ complete: false });
  const r = await m.t.send(Buffer.from("{}"), ctx());
  m.t.close();
  assert.equal(r.failure, "INCOMPLETE_HTTP_RESPONSE");
});

test("trailers are preserved and included in header limits", async()=>{
 for(const size of [10,9000]){const m=mock({rawTrailers:["X-Backend", "a".repeat(size)]});const r=await m.t.send(Buffer.from("{}"),ctx());m.t.close();
 if(size===10){assert.equal(r.failure,undefined);assert.equal(JSON.parse(r.headers).trailers[0],"X-Backend");}else{assert.equal(r.failure,"HEADER_LIMIT");assert.equal(r.headers.length,8192);}}
});
test("reused TLS socket records existing authorization without handshake listeners",async()=>{
 const m=mock({reusedSocket:true});for(let i=0;i<19;i++){const r=await m.t.send(Buffer.from("{}"),ctx());assert.equal(r.connection.tlsAuthorized,true);assert.equal(r.connection.id,1);}m.t.close();assert.equal(m.counts().socket.listenerCount("secureConnect"),0);
});
