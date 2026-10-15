import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
test('scanner and observer share byte-identical entry context validation',()=>{
 assert.equal(fs.readFileSync(new URL('../scanner/src/core/entry-context.js',import.meta.url),'utf8'),fs.readFileSync(new URL('../quote-observer/entry-context.mjs',import.meta.url),'utf8'));
});
