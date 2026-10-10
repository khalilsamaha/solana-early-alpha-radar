import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { scoreCandidate, deriveMetrics } from '../src/core/scoring.js';
const fixtures = JSON.parse(fs.readFileSync(new URL('../fixtures/scoring-cases.json', import.meta.url),'utf8'));

test('early breakout scores as strong/exceptional', () => {
  const f = fixtures[0];
  const s = scoreCandidate(f.current,f.previous,f.now);
  assert.ok(s.score >= 82, `score was ${s.score}`);
});

test('suspicious launch is hard-capped below alert threshold', () => {
  const f = fixtures[1];
  const s = scoreCandidate(f.current,null,f.now);
  assert.ok(s.score < 50, `score was ${s.score}`);
  assert.equal(s.band,'low');
});

test('ordinary token does not trigger strong signal', () => {
  const f = fixtures[2];
  const s = scoreCandidate(f.current,null,f.now);
  assert.ok(s.score < 72, `score was ${s.score}`);
});

test('derives buy/sell and turnover metrics', () => {
  const f = fixtures[0];
  const m = deriveMetrics(f.current,f.previous,f.now);
  assert.equal(m.txns5m,99);
  assert.ok(m.buySellRatio > 2.5);
  assert.ok(m.volumeLiquidity > 1);
  assert.ok(m.volumeAcceleration > 0);
});
