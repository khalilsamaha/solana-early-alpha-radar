import test from 'node:test';
import assert from 'node:assert/strict';
import {alertQualityLabel} from '../public/alert-quality.js';
import {formatAlert} from '../src/adapters/telegram.js';
const fixture=liquidityUsd=>({id:'test',at:1800000000000,candidate:{symbol:'TEST',mint:'So11111111111111111111111111111111111111112',liquidityUsd},
 scoring:{score:73,metrics:{ageMin:1,buys5m:10,sells5m:5}},qualification:{state:'deteriorating',disposition:'defer',reasons:[],historyReady:true}});
test('high score does not hide deferred entry quality and unknown liquidity is not zero',()=>{
 const a=fixture(null),before=structuredClone(a),s=formatAlert(a);
 assert.match(s,/Research only: shadow defer/);assert.match(s,/Activity score: 73/);assert.match(s,/Liquidity: unknown/);
 assert.deepEqual(a,before);assert.match(formatAlert(fixture(0)),/Liquidity: \$0/);
});
test('retained and missing qualification never imply execution approval',()=>{
 assert.match(alertQualityLabel({disposition:'retain'}),/Execution and safety are not verified/);
 assert.match(alertQualityLabel(null),/qualification unavailable/);
 assert.equal(formatAlert({text:'Health message'}),'Health message');
});
