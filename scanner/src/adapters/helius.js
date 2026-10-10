async function rpc(mint,key,http,method,params) {
  const body=await http.json('helius',`https://mainnet.helius-rpc.com/?api-key=${encodeURIComponent(key)}`,{
    method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params})});
  return body.result;
}
export async function getMintSecurity(mint,key,http) {
  const account=await rpc(mint,key,http,'getAccountInfo',[mint,{encoding:'jsonParsed',commitment:'confirmed'}]);
  const parsed=account?.value?.data?.parsed;
  if(parsed?.type!=='mint'||!parsed.info||!('mintAuthority' in parsed.info)||!('freezeAuthority' in parsed.info))throw new Error('Mint authority data unavailable');
  const info=parsed.info;
  const largest=await rpc(mint,key,http,'getTokenLargestAccounts',[mint,{commitment:'confirmed'}]);
  const supply=BigInt(info.supply||'0');
  if(supply<=0n||!Array.isArray(largest?.value))throw new Error('Token supply/concentration unavailable');
  const total=largest.value.slice(0,10).reduce((s,x)=>s+BigInt(x.amount),0n);
  const top10Pct=Number(total*1000000n/supply)/10000;
  const extensions=(info.extensions||[]).map(x=>x.extension);
  return {mintAuthority:info.mintAuthority,freezeAuthority:info.freezeAuthority,top10Pct,
    concentrationMethod:'top10-token-accounts-unadjusted',tokenProgram:account.value.owner,
    extensions,securityCheckedAt:Date.now()};
}
