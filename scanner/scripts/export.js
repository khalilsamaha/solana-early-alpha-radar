import {config} from '../src/config.js';
import {Storage} from '../src/core/storage.js';
const kind=process.argv[2]||'outcomes';
if(!['outcomes','alerts','snapshots','exit-alerts'].includes(kind))throw new Error('Unsupported export kind');
const storage=new Storage(config.dataDir);
try{for(const event of storage.events(kind))console.log(JSON.stringify(event));}finally{storage.close();}
