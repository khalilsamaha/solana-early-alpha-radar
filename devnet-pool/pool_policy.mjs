// Fixed devnet instruction compiler; no I/O, signing or network.
import {createHash} from 'node:crypto';
const check=v=>{if(!v)throw new Error('pool-policy');};
const alpha='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
export function raw58(s){check(typeof s==='string'&&s.length>=32&&s.length<=44);let n=0n;for(const c of s){check(alpha.includes(c));n=n*58n+BigInt(alpha.indexOf(c));}
 let h=n.toString(16);if(h.length%2)h='0'+h;const b=Buffer.concat([Buffer.alloc(s.match(/^1*/)[0].length),n?Buffer.from(h,'hex'):Buffer.alloc(0)]);check(b.length===32);return b;}
function b58(b){let n=BigInt('0x'+b.toString('hex'));let s='';while(n){s=alpha[Number(n%58n)]+s;n/=58n;}let z=0;while(z<b.length&&b[z]===0)z++;return '1'.repeat(z)+s;}
const hash=b=>createHash('sha256').update(b).digest();
const P=2n**255n-19n;const mod=n=>((n%P)+P)%P;
function pow(n,e){let r=1n;n=mod(n);while(e){if(e&1n)r=r*n%P;n=n*n%P;e>>=1n;}return r;}
const D=mod(-121665n*pow(121666n,P-2n));
export function onCurve(b){check(b.length===32);const copy=Buffer.from(b);copy[31]&=127;const y=BigInt('0x'+copy.reverse().toString('hex'))%P;const den=mod(D*y*y+1n);if(!den)return false;const x=mod((y*y-1n)*pow(den,P-2n));return x===0n||pow(x,(P-1n)/2n)===1n;}
export function pda(seeds,program){check(seeds.length<16&&seeds.every(s=>s.length<=32));for(let b=255;b>=0;b--){const h=hash(Buffer.concat([...seeds,Buffer.from([b]),raw58(program),Buffer.from('ProgramDerivedAddress')]));if(!onCurve(h))return [b58(h),b];}throw new Error('pda-unavailable');}
const PROGRAM='DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb',TOKEN='TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';
const CONFIG='8Pg5wr9H5i2GKbiH8315UiM1W9LJQT2tNiuqBeaoGKjz',AUTH='CXniRufdq5xL8t8jZAPxsPZDpuudwuJSPWnbcD5Y5Nxq';
const ATA='ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL',COMPUTE='ComputeBudget111111111111111111111111111111';
export const roles=['wallet','pool','lpMint','holder0','holder1','lpHolder','vault0','vault1','feeReceiver','observation','config','authority','mint0','mint1','tokenProgram','associatedTokenProgram','systemProgram','rent','program','compute'];
const ixRoles=['wallet','config','authority','pool','mint0','mint1','lpMint','holder0','holder1','lpHolder','vault0','vault1','feeReceiver','observation','tokenProgram','tokenProgram','tokenProgram','associatedTokenProgram','systemProgram','rent'];
export function addresses(pair){
 check(pair&&Object.keys(pair).sort().join('|')===['wallet','mintA','holderA','mintB','holderB'].sort().join('|'));
 Object.values(pair).forEach(raw58);check(new Set(Object.values(pair)).size===5);
 const ordered=[[pair.mintA,pair.holderA],[pair.mintB,pair.holderB]].sort((a,b)=>Buffer.compare(raw58(a[0]),raw58(b[0])));
 const [[m0,h0],[m1,h1]]=ordered;const derive=s=>pda(s,PROGRAM)[0];
 const pool=derive([Buffer.from('pool'),raw58(CONFIG),raw58(m0),raw58(m1)]),lp=derive([Buffer.from('pool_lp_mint'),raw58(pool)]);
 const a={wallet:pair.wallet,pool,lpMint:lp,holder0:h0,holder1:h1,lpHolder:pda([raw58(pair.wallet),raw58(TOKEN),raw58(lp)],ATA)[0],
 vault0:derive([Buffer.from('pool_vault'),raw58(pool),raw58(m0)]),vault1:derive([Buffer.from('pool_vault'),raw58(pool),raw58(m1)]),
 feeReceiver:'3oE58BKVt8KuYkGxx8zBojugnymWmBiyafWgMrnb6eYy',observation:derive([Buffer.from('observation'),raw58(pool)]),
 config:CONFIG,authority:AUTH,mint0:m0,mint1:m1,tokenProgram:TOKEN,associatedTokenProgram:ATA,systemProgram:'11111111111111111111111111111111',
 rent:'SysvarRent111111111111111111111111111111111',program:PROGRAM,compute:COMPUTE};
 check(new Set(Object.values(a)).size===20);check(pda([Buffer.from('vault_and_lp_mint_auth_seed')],PROGRAM).join('|')===AUTH+'|255');return a;
}
export function message(pair,blockhash){const a=addresses(pair);const keys=roles.map(r=>a[r]);
 const u64=n=>{const b=Buffer.alloc(8);b.writeBigUInt64LE(BigInt(n));return b;};
 const ix=(program,rs,data)=>Buffer.concat([Buffer.from([keys.indexOf(program),rs.length,...rs.map(r=>roles.indexOf(r)),data.length]),data]);
 const cu=Buffer.alloc(5);cu[0]=2;cu.writeUInt32LE(300000,1);
 const ops=[ix(COMPUTE,[],cu),ix(COMPUTE,[],Buffer.concat([Buffer.from([3]),Buffer.alloc(8)])),ix(PROGRAM,ixRoles,Buffer.concat([hash(Buffer.from('global:initialize')).subarray(0,8),u64(500000000),u64(500000000),u64(0)]))];
 return Buffer.concat([Buffer.from([1,0,10,20]),...keys.map(raw58),raw58(blockhash),Buffer.from([3]),...ops]);
}
