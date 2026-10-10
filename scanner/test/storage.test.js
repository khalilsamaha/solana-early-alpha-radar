import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Storage } from '../src/core/storage.js';

test('storage persists candidates and JSONL events', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(),'radar-'));
  const s = new Storage(dir);
  s.saveCandidates({abc:{mint:'abc'}});
  assert.equal(s.loadCandidates().abc.mint,'abc');
  s.append('alerts',{id:1});
  s.append('alerts',{id:2});
  assert.deepEqual(s.readJsonl('alerts').map(x=>x.id),[1,2]);
});
