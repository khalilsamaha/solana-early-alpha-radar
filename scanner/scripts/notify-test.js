import {config} from '../src/config.js';
import {sendTelegram} from '../src/adapters/telegram.js';
const alert={id:`test:${Date.now()}`,at:Date.now(),text:'Solana Radar: notification test. Paper monitoring only.'};
if(!process.argv.includes('--send'))console.log('Preview only:',alert.text,'\nUse --send to send one test to your configured TELEGRAM_CHAT_ID.');
else {
  if(!config.notificationsEnabled)throw new Error('Set NOTIFICATIONS_ENABLED=true before sending');
  const r=await sendTelegram(config,alert);console.log(r.skipped?'Skipped':'Telegram accepted the test message.');
}
