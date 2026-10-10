const BASE='https://api.jup.ag/tokens/v2';
const n=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))?Number(v):undefined;
async function query(route,key,http) {
  const rows=await http.json('jupiter',`${BASE}${route}`,{headers:{'x-api-key':key}});
  if(!Array.isArray(rows))throw new Error('Jupiter response is not an array');
  return rows;
}
export const getRecent=(key,http)=>query('/recent',key,http);
export const getTopOrganic=(key,http)=>query('/toporganicscore/5m',key,http);
export async function searchToken(mint,key,http) {
  const rows=await query(`/search?query=${encodeURIComponent(mint)}`,key,http);
  const row=rows.find(x=>(x.id||x.address||x.mint)===mint);
  return row?normalizeDiscoveryRow(row):null;
}
export function normalizeDiscoveryRow(row) {
  return {mint:row?.id||row?.address||row?.mint,tokenName:row?.name,symbol:row?.symbol,
    organicScore:n(row?.organicScore),holderCount:n(row?.holderCount),
    auditIsSus:typeof row?.audit?.isSus==='boolean'?row.audit.isSus:undefined,
    firstPoolAt:Date.parse(row?.firstPool?.createdAt)||undefined,
    isVerified:row?.isVerified===true,jupiterStats:row?.stats5m};
}
