// Shared by the browser and Telegram. Destinations never come from token metadata.
export const validSolanaAddress=value=>typeof value==='string'&&/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(value);
export function tokenLinks(candidate={}) {
  candidate??={};
  if(!validSolanaAddress(candidate.mint)||(candidate.chainId&&candidate.chainId!=='solana'))return [];
  const mint=encodeURIComponent(candidate.mint);
  const links=[
    {label:'Phantom',url:`https://phantom.com/tokens/solana/${mint}`},
    {label:'Jupiter',url:`https://jup.ag/tokens/${mint}`},
  ];
  if(validSolanaAddress(candidate.pairAddress))links.push({label:'DEX Screener',url:`https://dexscreener.com/solana/${encodeURIComponent(candidate.pairAddress)}`});
  links.push({label:'Solscan',url:`https://solscan.io/token/${mint}`});
  return links;
}
