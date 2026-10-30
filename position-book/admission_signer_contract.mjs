// Independent fixed devnet message reconstruction. No keys, filesystem or RPC.
import crypto from 'node:crypto';
import {addresses, raw58} from '../devnet-pool/pool_policy.mjs';
export const check = v => { if (!v) throw new Error('admission-signer-refused'); };
export function canonical(v) {
  if (Array.isArray(v)) return v.map(canonical);
  if (v && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical(v[k])]));
  return v;
}
export const text = v => JSON.stringify(canonical(v));
export const hash = v => crypto.createHash('sha256').update(text(v)).digest('hex');
export const bytesHash = v => crypto.createHash('sha256').update(v).digest('hex');
const fields = (v, names) => check(v && !Array.isArray(v) && Object.keys(v).sort().join('|') === [...names].sort().join('|'));
const num = (n, lo, hi) => check(Number.isSafeInteger(n) && n >= lo && n <= hi);
const digest = s => check(typeof s === 'string' && /^[a-f0-9]{64}$/.test(s));
function atomic(s, positive = false) {
  check(typeof s === 'string' && /^(0|[1-9][0-9]{0,19})$/.test(s));
  const n = BigInt(s); check(n >= (positive ? 1n : 0n) && n <= 2n ** 64n - 1n); return n;
}
const alpha = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
function b58(b) {
  let n = BigInt('0x' + b.toString('hex')), out = '', z = 0;
  while (n) { out = alpha[Number(n % 58n)] + out; n /= 58n; }
  while (z < b.length && b[z] === 0) z++;
  return '1'.repeat(z) + out;
}
export const roles = ['wallet','authority','config','pool','source','destination','inputVault','outputVault','inputMint','outputMint','observation'];
const stable = ['network','accounts','amountIn','minimumAmountOut','maxComputeUnits','maxMicroLamportsPerCU','maxPriorityFeeLamports','maxTotalFeeLamports'];
const TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';
const PROGRAM = 'DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb';
const COMPUTE = 'ComputeBudget111111111111111111111111111111';
export function compile(scope, blockhash) {
  fields(scope, ['format', ...stable]); check(scope.format === 'devnet-swap-scope-1' && scope.network === 'devnet');
  fields(scope.accounts, roles); Object.values(scope.accounts).forEach(raw58); raw58(blockhash);
  check(Object.values(scope.accounts).every(k => !['So11111111111111111111111111111111111111112','11111111111111111111111111111111'].includes(k)));
  const input = atomic(scope.amountIn, true), minimum = atomic(scope.minimumAmountOut, true);
  check(input <= 1000n && atomic(scope.maxTotalFeeLamports, true) <= 10000n);
  num(scope.maxComputeUnits, 1, 300000);
  check(scope.maxMicroLamportsPerCU === '0' && scope.maxPriorityFeeLamports === '0');
  const a = scope.accounts, writable = new Set(['wallet','pool','source','destination','inputVault','outputVault','observation']);
  const keys = [...roles.filter(k => writable.has(k)).map(k => a[k]), ...roles.filter(k => !writable.has(k)).map(k => a[k]), TOKEN, PROGRAM, COMPUTE];
  check(new Set(keys).size === 14);
  const u64 = n => { const b = Buffer.alloc(8); b.writeBigUInt64LE(n); return b; };
  const cu = Buffer.alloc(5); cu[0] = 2; cu.writeUInt32LE(scope.maxComputeUnits, 1);
  const ixRoles = ['wallet','authority','config','pool','source','destination','inputVault','outputVault','inputTokenProgram','outputTokenProgram','inputMint','outputMint','observation'];
  const all = {...a, inputTokenProgram: TOKEN, outputTokenProgram: TOKEN};
  const ops = [
    {programIdIndex: keys.indexOf(COMPUTE), accounts: [], raw: cu},
    {programIdIndex: keys.indexOf(COMPUTE), accounts: [], raw: Buffer.concat([Buffer.from([3]), Buffer.alloc(8)])},
    {programIdIndex: keys.indexOf(PROGRAM), accounts: ixRoles.map(k => keys.indexOf(all[k])),
      raw: Buffer.concat([Buffer.from('8fbe5adac41e33de','hex'), u64(input), u64(minimum)])}
  ];
  const message = Buffer.concat([Buffer.from([1,0,7,14]), ...keys.map(raw58), raw58(blockhash), Buffer.from([3]),
    ...ops.map(o => Buffer.concat([Buffer.from([o.programIdIndex, o.accounts.length, ...o.accounts, o.raw.length]), o.raw]))]);
  const parsed = {bindingVersion:'canonical-message-binding-1',version:'legacy',message:{
    accountKeys:keys,header:{numRequiredSignatures:1,numReadonlySignedAccounts:0,numReadonlyUnsignedAccounts:7},
    recentBlockhash:blockhash,addressTableLookups:[],instructions:ops.map(o => ({programIdIndex:o.programIdIndex,accounts:o.accounts,data:b58(o.raw)}))},
    loadedAddresses:{writable:[],readonly:[]}};
  return {message, unsigned:Buffer.concat([Buffer.from([1]),Buffer.alloc(64),message]).toString('base64'), canonicalHash:hash(parsed)};
}

export function validate(policy, rows, metadata, pair, requestedHash, now) {
  fields(policy, ['format','scope','maximumExitAttempts','maximumExitFeeLamports','maximumTotalFeeLamports']);
  check(policy.format === 'pre-sign-admission-1-policy'); num(policy.maximumExitAttempts, 1, 3);
  const exit = atomic(policy.maximumExitFeeLamports, true), total = atomic(policy.maximumTotalFeeLamports, true);
  check(exit <= 10000n && total <= 40000n); digest(requestedHash);
  check(metadata.format === 'devnet-wallet-1' && metadata.network === 'devnet' && metadata.purpose === 'fixed-self-transfer-rehearsal');
  const derived = addresses(pair), mapping = {source:'holder0',destination:'holder1',inputVault:'vault0',outputVault:'vault1',inputMint:'mint0',outputMint:'mint1'};
  const a = policy.scope.accounts;
  check(metadata.wallet === a.wallet && roles.every(k => a[k] === derived[mapping[k] || k]));
  // This new backend accepts exactly the initial reserve/arm/boundary sequence.
  check(rows.length === 3); let previous = '', last = 0;
  const states = rows.map((row, i) => {
    num(row.at_ms, last, now); check(row.seq === i+1 && typeof row.value === 'string' && row.value.length <= 8192);
    const value = JSON.parse(row.value); check(text(value) === row.value && value.policySha256 === hash(policy));
    check(row.previous_hash === previous && row.hash === hash({seq:i+1,atMs:row.at_ms,value,previousHash:previous}));
    previous = row.hash; last = row.at_ms; return value;
  });
  const [first, armed, s] = states;
  fields(first,['evidenceSha256','policySha256','messageSha256','ledgerHeadSha256','cycleBindingSha256','validUntilExclusiveMs',
    'reservedPrincipalAtomic','reservedFeeLamports','maximumExitAttempts','entryFeeCapLamports','exitFeeCapLamports','state','reservedAtMs','signingBoundaryAtMs']);
  check(first.state === 'reserved' && first.signingBoundaryAtMs === null);
  const req = armed.signingRequest;
  check(armed.signingRequestSha256 === hash(req) && hash(req) === requestedHash);
  check(text(armed) === text({...first,signingRequest:req,signingRequestSha256:requestedHash}));
  check(text(s) === text({...armed,state:'signing-unknown',signingBoundaryAtMs:s.signingBoundaryAtMs}));
  num(first.reservedAtMs,1,rows[0].at_ms); num(s.signingBoundaryAtMs,rows[1].at_ms,rows[2].at_ms);
  fields(req,['format','network','policySha256','evidenceSha256','messageSha256','validUntilExclusiveMs','packet','receiptIntentTemplate']);
  check(req.format === 'entry-handoff-1-sign-request' && req.network === 'devnet');
  for (const k of ['policySha256','evidenceSha256','messageSha256']) {digest(s[k]); check(req[k] === s[k]);}
  digest(s.ledgerHeadSha256); digest(s.cycleBindingSha256);
  check(s.maximumExitAttempts === policy.maximumExitAttempts && s.exitFeeCapLamports === policy.maximumExitFeeLamports &&
    s.entryFeeCapLamports === policy.scope.maxTotalFeeLamports && s.reservedPrincipalAtomic === policy.scope.amountIn);
  check(atomic(s.reservedFeeLamports) === atomic(s.entryFeeCapLamports) + BigInt(policy.maximumExitAttempts)*exit && atomic(s.reservedFeeLamports) <= total);
  const packet = req.packet; fields(packet,['format','policy','unsignedTransactionBase64','feeAssertion']);
  check(packet.format === 'unsigned-cpmm-contract-1'); const p = packet.policy;
  fields(p,['format','issuedAtMs','expiresAtMs','blockhash',...stable]); check(p.format === 'cpmm-instruction-policy-1');
  check(stable.every(k => text(p[k]) === text(policy.scope[k])));
  num(p.issuedAtMs,1,first.reservedAtMs); num(p.expiresAtMs,now+1,p.issuedAtMs+15000);
  check(req.validUntilExclusiveMs === s.validUntilExclusiveMs); num(s.validUntilExclusiveMs,now+1,p.expiresAtMs);
  const built = compile(policy.scope,p.blockhash), fee = packet.feeAssertion;
  check(packet.unsignedTransactionBase64 === built.unsigned && bytesHash(built.message) === s.messageSha256);
  fields(fee,['format','network','messageSha256','observedAtMs','lamports']);
  check(fee.format === 'message-fee-assertion-1' && fee.network === 'devnet' && fee.messageSha256 === s.messageSha256);
  num(fee.observedAtMs,p.issuedAtMs,first.reservedAtMs); check(now-fee.observedAtMs <= 10000 && atomic(fee.lamports,true) <= atomic(s.entryFeeCapLamports));
  const t = req.receiptIntentTemplate;
  fields(t,['format','network','wallet','messageSha256','preparedAtMs','walletPreLamports','source','destination','inputAtomic','minimumOutputAtomic','maximumFeeLamports','maximumRentLamports']);
  check(t.format === 'transaction-intent-1' && t.network === 'devnet' && t.wallet === a.wallet &&
    t.messageSha256 === built.canonicalHash && t.preparedAtMs === p.issuedAtMs &&
    t.inputAtomic === p.amountIn && t.minimumOutputAtomic === p.minimumAmountOut &&
    t.maximumFeeLamports === s.entryFeeCapLamports && t.maximumRentLamports === '0');
  check(atomic(t.walletPreLamports) >= atomic(s.reservedFeeLamports));
  for (const [side,mint] of [['source','inputMint'],['destination','outputMint']]) {
    const r=t[side]; fields(r,['account','mint','programId','decimals','preAmountAtomic','lifecycle']);
    check(r.account === a[side] && r.mint === a[mint] && r.programId === TOKEN && r.lifecycle === 'existing');
    num(r.decimals,0,18); atomic(r.preAmountAtomic);
  }
  check(atomic(t.source.preAmountAtomic) >= atomic(p.amountIn));
  return {message:built.message, wallet:a.wallet, deadline:s.validUntilExclusiveMs, notBeforeMs:last, requestHash:requestedHash, admissionHead:previous};
}
