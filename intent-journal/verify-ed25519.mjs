// Verification only. Reads public bytes on stdin; no signing or network imports.
import {createPublicKey, verify} from 'node:crypto';
let input = '';
try {
  for await (const chunk of process.stdin) {
    input += chunk;
    if (input.length > 8192) throw new Error('cap');
  }
  const data = JSON.parse(input);
  const decode = (s, size) => {
    if (typeof s !== 'string') throw new Error('shape');
    const b = Buffer.from(s, 'base64');
    if (b.toString('base64') !== s || (size && b.length !== size)) throw new Error('encoding');
    return b;
  };
  const message = decode(data.message);
  if (!message.length || message.length > 1232 || !Array.isArray(data.signers) ||
      !data.signers.length || data.signers.length > 18) throw new Error('shape');
  const valid = data.signers.every(s => {
    const key = createPublicKey({key: Buffer.concat([
      Buffer.from('302a300506032b6570032100', 'hex'), decode(s.key, 32)
    ]), format: 'der', type: 'spki'});
    return verify(null, message, key, decode(s.signature, 64));
  });
  process.stdout.write(JSON.stringify({valid}));
} catch {
  process.stdout.write(JSON.stringify({valid: false}));
  process.exitCode = 1;
}
