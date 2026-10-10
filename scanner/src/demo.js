import { scoreCandidate } from './core/scoring.js';
import fs from 'node:fs';
const fixtures = JSON.parse(fs.readFileSync(new URL('../fixtures/scoring-cases.json', import.meta.url),'utf8'));
for (const f of fixtures) {
  const result = scoreCandidate(f.current, f.previous || null, f.now);
  console.log(`\n${f.name}: ${result.score}/100 (${result.band})`);
  console.log('  +' + result.reasons.slice(0,6).map(x=>`${x.pts} ${x.reason}`).join('\n  +'));
  if (result.risks.length) console.log('  risks: ' + result.risks.map(x=>x.reason).join('; '));
}
