import path from 'node:path';
import fs from 'node:fs';
import {config} from '../src/config.js';
import {Storage} from '../src/core/storage.js';
const dest=path.resolve(process.argv[2]||`backups/radar-${new Date().toISOString().replace(/[:.]/g,'-')}.sqlite`);
fs.mkdirSync(path.dirname(dest),{recursive:true,mode:0o700});
if(fs.existsSync(dest))throw new Error('Backup destination already exists');
const storage=new Storage(config.dataDir);
try{await storage.backup(dest);console.log(`Backup saved: ${dest}`);}finally{storage.close();}
