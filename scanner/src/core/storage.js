import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync, backup } from 'node:sqlite';
import { randomUUID } from 'node:crypto';

export class Storage {
  constructor(dir) {
    this.dir = dir;this.writes={transactions:0,stateAttempts:0,stateChanged:0,candidateAttempts:0,candidateChanged:0};
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    this.db = new DatabaseSync(path.join(dir, 'radar.sqlite'));
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS candidates(mint TEXT PRIMARY KEY, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, id TEXT NOT NULL, at INTEGER NOT NULL, data TEXT NOT NULL, UNIQUE(kind,id));
      CREATE INDEX IF NOT EXISTS events_kind_seq ON events(kind,seq);
      CREATE INDEX IF NOT EXISTS events_at ON events(kind,at);
      CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, at INTEGER NOT NULL, next_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, payload TEXT NOT NULL, last_error TEXT, delivered_at INTEGER);
      CREATE INDEX IF NOT EXISTS outbox_due ON outbox(status,next_at);`);
    try{this.importLegacy();}catch(error){this.db.close();throw error;}
  }
  transaction(fn) {
    if(this.inTransaction)return fn();
    this.db.exec('BEGIN IMMEDIATE');this.inTransaction=true;
    try { const result = fn(); this.db.exec('COMMIT');this.writes.transactions++; return result; }
    catch (error) { this.db.exec('ROLLBACK'); throw error; }
    finally {this.inTransaction=false;}
  }
  loadCandidates() { return Object.fromEntries(this.db.prepare('SELECT mint,data FROM candidates').all().map(r=>[r.mint,JSON.parse(r.data)])); }
  saveCandidate(row) { this.writes.candidateAttempts++;const r=this.db.prepare('INSERT INTO candidates(mint,data) VALUES (?,?) ON CONFLICT(mint) DO UPDATE SET data=excluded.data WHERE candidates.data<>excluded.data').run(row.mint, JSON.stringify(row));this.writes.candidateChanged+=Number(r.changes); }
  saveCandidates(obj) { this.transaction(()=>{ for (const row of Object.values(obj)) this.saveCandidate(row); }); }
  deleteCandidate(mint) { this.db.prepare('DELETE FROM candidates WHERE mint=?').run(mint); }
  append(kind, obj) {
    const id = String(obj.id ?? (kind === 'outcomes' ? `${obj.mint}:${obj.alertAt}:${obj.horizon}` : randomUUID()));
    this.db.prepare('INSERT OR IGNORE INTO events(kind,id,at,data) VALUES (?,?,?,?)').run(kind,id,obj.at ?? Date.now(),JSON.stringify(obj));
  }
  readJsonl(kind, limit=2000) {
    return this.db.prepare('SELECT data FROM events WHERE kind=? ORDER BY seq DESC LIMIT ?').all(kind,Math.max(1,Math.min(100000,Math.floor(limit)||2000))).reverse().map(r=>JSON.parse(r.data));
  }
  *events(kind) { for (const r of this.db.prepare('SELECT data FROM events WHERE kind=? ORDER BY seq').iterate(kind)) yield JSON.parse(r.data); }
  getState(key='state') { const r=this.db.prepare('SELECT data FROM kv WHERE key=?').get(key); return r ? JSON.parse(r.data) : {}; }
  setState(state,key='state') { this.writes.stateAttempts++;const r=this.db.prepare('INSERT INTO kv(key,data) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data WHERE kv.data<>excluded.data').run(key,JSON.stringify(state));this.writes.stateChanged+=Number(r.changes); }
  writeStats(){return {...this.writes,stateUnchanged:this.writes.stateAttempts-this.writes.stateChanged,candidateUnchanged:this.writes.candidateAttempts-this.writes.candidateChanged};}
  queue(payload) {
    this.db.prepare("INSERT OR IGNORE INTO outbox(id,at,next_at,status,payload) VALUES (?,?,?,'pending',?)").run(payload.id,payload.at,payload.at,JSON.stringify(payload));
  }
  recordAlert(candidate,alert,notify) { this.transaction(()=>{this.saveCandidate(candidate);this.setState({paperEntry:candidate.paperEntry,alertLevel:candidate.alertLevel,alertedAt:candidate.alertedAt,decisionTimeline:candidate.decisionTimeline},`paper:${candidate.mint}`);this.append('alerts',alert);if(notify)this.queue(alert);}); }
  dueNotifications(now) { return this.db.prepare("SELECT * FROM outbox WHERE status='pending' AND next_at<=? ORDER BY at LIMIT 20").all(now).map(r=>({...r,payload:JSON.parse(r.payload)})); }
  updateNotification(id,{status,attempts,nextAt,error=null,deliveredAt=null}) {
    this.db.prepare('UPDATE outbox SET status=?,attempts=?,next_at=?,last_error=?,delivered_at=? WHERE id=?').run(status,attempts,nextAt,error,deliveredAt,id);
  }
  notificationStats() { return Object.fromEntries(this.db.prepare('SELECT status,count(*) AS count FROM outbox GROUP BY status').all().map(r=>[r.status,r.count])); }
  prune(before) { this.db.prepare("DELETE FROM events WHERE kind IN ('snapshots','decisions','research-events','research-entries','research-outcomes','fast-shadow-entries','fast-shadow-outcomes','fast-shadow-links') AND at<?").run(before);
    this.db.prepare("DELETE FROM kv WHERE (key LIKE 'research:%' OR key LIKE 'fast-shadow:%') AND json_extract(data,'$.updatedAt')<?").run(before);
  }
  async backup(file) { await backup(this.db, file); }
  close() { this.db.close(); }
  importLegacy() {
    if (this.getState('migration').done) return;
    this.transaction(()=>{
      const cfile=path.join(this.dir,'candidates.json');
      if(fs.existsSync(cfile)) {
        for(const row of Object.values(JSON.parse(fs.readFileSync(cfile,'utf8')))) {
          if(row.paperEntry) row.paperEntry.legacy=true;
          this.saveCandidate(row);
        }
      }
      for(const kind of ['alerts','outcomes','snapshots']) {
        const file=path.join(this.dir,`${kind}.jsonl`);
        if(!fs.existsSync(file))continue;
        const lines=fs.readFileSync(file,'utf8').split(/\r?\n/);
        for(let i=0;i<lines.length;i++) {
          if(!lines[i].trim())continue;
          try { const row=JSON.parse(lines[i]); row.legacy=true; this.append(kind,row); }
          catch { throw new Error(`Legacy import aborted: ${kind}.jsonl line ${i+1} is invalid. Original files are unchanged.`); }
        }
      }
      this.setState({done:true,at:Date.now()},'migration');
    });
  }
}
