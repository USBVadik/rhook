import net from 'node:net';
import dns from 'node:dns';
const denied = () => { throw new Error('OFFLINE_TEST_NETWORK_FORBIDDEN'); };
net.Socket.prototype.connect = denied;
dns.lookup = denied;
globalThis.fetch = denied;
