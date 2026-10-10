import {sendTelegram} from '../adapters/telegram.js';
export class Notifications {
  constructor(config,storage,send=sendTelegram){Object.assign(this,{config,storage,send});this.busy=false;}
  async flush(now=Date.now()) {
    if(this.busy||!this.config.notificationsEnabled)return;
    if((this.storage.getState('telegram').retryUntil||0)>now)return;
    this.busy=true;
    try {
      for(const row of this.storage.dueNotifications(now)) {
        const attempts=row.attempts+1;
        if((row.payload.type==='research'&&(!this.config.researchEnabled||!this.config.researchNotifications))||now-row.at>this.config.notifyTtlMs||(row.payload.expiresAt&&now>row.payload.expiresAt)) {
          this.storage.updateNotification(row.id,{status:'expired',attempts:row.attempts,nextAt:now});continue;
        }
        try {
          const result=await this.send(this.config,row.payload);
          if(result?.skipped)throw new Error('Notification channel unavailable');
          this.storage.updateNotification(row.id,{status:'sent',attempts,nextAt:now,deliveredAt:Date.now()});
        } catch(error) {
          if(error.retryAfterMs)this.storage.setState({retryUntil:now+error.retryAfterMs},'telegram');
          const delay=Math.max(error.retryAfterMs||0,Math.min(300000,1000*2**attempts));
          this.storage.updateNotification(row.id,{status:error.permanent||attempts>=8?'failed':'pending',attempts,nextAt:now+delay,error:String(error.message).replace(/https?:\/\/\S+/g,'[redacted URL]').slice(0,160)});
          break; // Global Telegram flood limit applies to subsequent messages too.
        }
      }
    } finally {this.busy=false;}
  }
}
