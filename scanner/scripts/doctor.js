import {config} from '../src/config.js';
import {Health} from '../src/core/health.js';
import {HttpClient} from '../src/core/http.js';
import {getLatestProfiles,getTokenPair} from '../src/adapters/dexscreener.js';
import {getRecent} from '../src/adapters/jupiter.js';
import {getMintSecurity} from '../src/adapters/helius.js';
console.log('Runtime:',process.version);
for(const [name,value] of Object.entries({PumpPortal:config.pumpPortalApiKey,Jupiter:config.jupiterApiKey,Helius:config.heliusApiKey,Telegram:config.telegramBotToken,DashboardAuth:config.dashboardToken}))console.log(`${name}: ${value?'configured':'not configured'}`);
if(process.argv.includes('--live')) {
  const health=new Health(config),http=new HttpClient(config,health);
  try {
    const profiles=await getLatestProfiles(http);console.log('DEX Solana profiles:',profiles.length);
    const mint=profiles[0]?.tokenAddress;
    if(mint){const pair=await getTokenPair(mint,http);console.log('DEX market:',pair?'matched base mint; price '+pair.priceUsd:'no matching pair');}
    if(config.jupiterApiKey)console.log('Jupiter recent rows:',(await getRecent(config.jupiterApiKey,http)).length);
    if(config.heliusApiKey&&mint){const s=await getMintSecurity(mint,config.heliusApiKey,http);console.log('Helius security fields returned:',Object.keys(s).join(', '));}
  }catch(error){console.error('Live check failed:',error.message);process.exitCode=1;}
}
console.log('Doctor never sends notifications, opens paid trade subscriptions, or trades.');
