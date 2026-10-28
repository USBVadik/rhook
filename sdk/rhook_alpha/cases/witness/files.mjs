import fs from "node:fs";
import path from "node:path";
function syncDir(dir) {
  const fd = fs.openSync(dir, fs.constants.O_RDONLY);
  try {
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
}
function writeNew(file, bytes) {
  const fd = fs.openSync(file, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 384);
  try {
    fs.writeFileSync(fd, bytes);
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  syncDir(path.dirname(file));
}
function checkEnvironment(env) {
  for (const k of ["NODE_OPTIONS", "NODE_PATH", "NODE_EXTRA_CA_CERTS", "NODE_TLS_REJECT_UNAUTHORIZED", "SSLKEYLOGFILE", "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]) if (env[k]) throw Error("UNSUPPORTED_ENVIRONMENT_" + k);
}

export {writeNew,checkEnvironment};
