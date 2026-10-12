import {attachFeed} from '../core/feed-evidence.js';
const BASE='https://api.dexscreener.com';
const choose=(rows,mint,preferred,locked=false)=>{
  const valid=rows.filter(p=>p?.chainId==='solana'&&p.baseToken?.address===mint&&typeof p.pairAddress==='string');
  return valid.find(p=>p.pairAddress===preferred)||(locked?null:valid.sort((a,b)=>(b.liquidity?.usd||0)-(a.liquidity?.usd||0))[0])||null;
};
// Return an observation for every requested mint, including explicit missing data.
// Paper positions use the exact original pool, even if another pool is now larger.
export async function getTokenPairs(candidates,http) {
  const result=new Map();
  for(let offset=0;offset<candidates.length;offset+=30) {
    const chunk=candidates.slice(offset,offset+30);
    const ordinary=chunk.filter(c=>!c.paperEntry?.pairAddress),pinned=chunk.filter(c=>c.paperEntry?.pairAddress);
    for(const [group,locked] of [[ordinary,false],[pinned,true]]) {
      if(!group.length)continue;
      const addresses=[...new Set(group.map(c=>locked?c.paperEntry.pairAddress:c.mint))];
      const url=locked?`${BASE}/latest/dex/pairs/solana/${addresses.map(encodeURIComponent).join(',')}`
        :`${BASE}/tokens/v1/solana/${addresses.map(encodeURIComponent).join(',')}`;
      let transport=null;
      const response=await http.json('dex',url,{},e=>{transport=e;}),observedAt=Date.now();
      const rows=locked?(response?.pairs===null?[]:response?.pairs):response;
      if(!Array.isArray(rows))throw new Error('DEX batch response is not an array');
      for(const c of group) {
        const pair=choose(rows,c.mint,c.paperEntry?.pairAddress||c.pairAddress,locked);
        result.set(c.mint,{market:attachFeed(pair?normalizePair(pair):null,transport,locked?'pairs-batch':'tokens-batch'),observedAt});
      }
    }
  }
  return result;
}
export async function getTokenPair(mint,http,pairAddress) {
  let transport=null;
  const rows=await http.json('dex',`${BASE}/token-pairs/v1/solana/${encodeURIComponent(mint)}`,{},e=>{transport=e;});
  if(!Array.isArray(rows))throw new Error('DEX pair response is not an array');
  const valid=rows.filter(p=>p.chainId==='solana'&&p.baseToken?.address===mint);
  const p=valid.find(p=>p.pairAddress===pairAddress)||valid.sort((a,b)=>(b.liquidity?.usd||0)-(a.liquidity?.usd||0))[0];
  return attachFeed(p?normalizePair(p):null,transport,'token-pairs');
}
export async function getLatestProfiles(http) {
  const rows=await http.json('dex',`${BASE}/token-profiles/latest/v1`);
  if(!Array.isArray(rows))throw new Error('DEX profiles response is not an array');
  return rows.filter(x=>x.chainId==='solana');
}
const n=v=>v!==null&&v!==''&&v!==undefined&&Number.isFinite(Number(v))?Number(v):undefined;
export function normalizePair(p) {
  const socials=p.info?.socials||[],websites=p.info?.websites||[];
  return {mint:p.baseToken.address,pairAddress:p.pairAddress,dexId:p.dexId,tokenName:p.baseToken.name,symbol:p.baseToken.symbol,
    quoteMint:p.quoteToken?.address,priceUsd:n(p.priceUsd),liquidityUsd:n(p.liquidity?.usd),marketCap:n(p.marketCap),fdv:n(p.fdv),
    pairCreatedAt:n(p.pairCreatedAt),txns:p.txns||{},volume:p.volume||{},priceChange:p.priceChange||{},
    socialCount:socials.length+websites.length,socials,websites,boostsActive:n(p.boosts?.active)||0,dexUrl:p.url};
}
