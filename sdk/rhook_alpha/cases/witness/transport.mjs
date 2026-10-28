import https from "node:https";
function createTransport({ endpoint, authorization = null, request = https.request, maxSockets = 1, agent = new https.Agent({ keepAlive: true, maxSockets, maxTotalSockets: maxSockets, maxFreeSockets: maxSockets }), now = () => process.hrtime.bigint() } = {}) {
  const sockets = /* @__PURE__ */ new WeakMap();
  let nextSocket = 0, closed = false;
  const send = (body, ctx) => new Promise((resolve) => {
    if (closed || ctx.signal?.aborted || now() >= ctx.deadline) {
      resolve({ status: null, body: Buffer.alloc(0), headers: Buffer.alloc(0), failure: ctx.signal?.aborted ? "CANCELLED" : "REQUEST_TIMEOUT" });
      return;
    }
    let req, res, timer, done = false, status = null, headers = Buffer.alloc(0), parts = [], length = 0, connection = null, bodyCap = 0;
    const captureHeaders = () => {
      const encoded = Buffer.from(JSON.stringify({initial: res.rawHeaders, trailers: res.rawTrailers ?? []}));
      const allowed = Math.max(0, Math.min(ctx.maxHeader, ctx.maxResponse - length));
      headers = encoded.subarray(0, allowed);
      return encoded.length <= allowed;
    };
    const finish = (failure) => {
      if (done) return;
      if (res && !captureHeaders()) failure = "HEADER_LIMIT";
      done = true;
      clearTimeout(timer);
      ctx.signal?.removeEventListener("abort", abort);
      if (failure) {
        res?.destroy();
        req?.destroy();
      }
      resolve({ status, headers, body: Buffer.concat(parts, length), connection, ...failure ? { failure } : {} });
    };
    const abort = () => finish("CANCELLED");
    timer = setTimeout(() => finish("REQUEST_TIMEOUT"), Math.max(1, Math.ceil(Number(ctx.deadline - now()) / 1e6)));
    ctx.signal?.addEventListener("abort", abort, { once: true });
    try {
      req = request(endpoint, { method: "POST", agent, maxHeaderSize: 8192, insecureHTTPParser: false, rejectUnauthorized: true, headers: { "Content-Type": "application/json", "Content-Length": String(body.length), "Accept-Encoding": "identity", "User-Agent": "RHOOK-case-capture/0.1", ...(authorization ? {Authorization: authorization} : {}) } }, (response) => {
        if (done) {
          response.destroy();
          return;
        }
        res = response;
        status = res.statusCode;
        if (!captureHeaders()) {
          finish("HEADER_LIMIT");
          return;
        }
        if (res.headers["content-encoding"] && res.headers["content-encoding"] !== "identity") {
          finish("UNEXPECTED_ENCODING");
          return;
        }
        bodyCap = Math.min(ctx.maxBody, ctx.maxResponse - headers.length);
        if (bodyCap <= 0) {
          finish("RESPONSE_BYTE_LIMIT");
          return;
        }
        const declared = res.headers["content-length"];
        if (declared !== void 0 && (!/^\d+$/.test(String(declared)) || BigInt(declared) > BigInt(bodyCap))) {
          finish("BODY_LIMIT");
          return;
        }
        res.on("error", (e) => finish(e.code === "HPE_HEADER_OVERFLOW" ? "HEADER_LIMIT" : "RESPONSE_STREAM_ERROR"));
        res.on("aborted", () => finish("RESPONSE_ABORTED"));
        res.on("readable", () => {
          while (!done && res.readableLength > 0) {
            const remaining = bodyCap - length;
            if (remaining <= 0) {
              finish("BODY_LIMIT");
              return;
            }
            const chunk = res.read(Math.min(res.readableLength, remaining));
            if (chunk === null) break;
            parts.push(chunk);
            length += chunk.length;
          }
          if (!done) res.read(0);
        });
        res.on("end", () => {
          if (!res.complete) finish("INCOMPLETE_HTTP_RESPONSE");
          else finish();
        });
        res.on("close", () => {
          if (!done) finish("INCOMPLETE_HTTP_RESPONSE");
        });
      });
      req.on("socket", (socket) => {
        if (!sockets.has(socket)) sockets.set(socket, ++nextSocket);
        connection = { id: sockets.get(socket), reused: Boolean(req.reusedSocket), remoteAddress: socket.remoteAddress ?? null, remotePort: socket.remotePort ?? null, tlsAuthorized: socket.authorized === true ? true : null };
        if (!req.reusedSocket && socket.authorized !== true) socket.once("secureConnect", () => {
          connection.remoteAddress = socket.remoteAddress ?? null;
          connection.remotePort = socket.remotePort ?? null;
          connection.tlsAuthorized = socket.authorized === true;
        });
      });
      req.on("error", (e) => finish(e.code === "HPE_HEADER_OVERFLOW" ? "HEADER_LIMIT" : "TRANSPORT_ERROR"));
      req.end(body);
    } catch {
      finish("TRANSPORT_ERROR");
    }
  });
  return { send, close: () => {
    closed = true;
    agent.destroy();
  } };
}
export {
  createTransport
};
