import test from 'node:test';
import assert from 'node:assert/strict';
import {errorEvidence} from './error-evidence.mjs';
import {parseQuote} from './quote-check.mjs';
test('nested objects, arrays and enum errors produce bounded diagnostic evidence',()=>{
 const r=errorEvidence({error:{details:[{message:'COULD_NOT_FIND_ANY_ROUTE',code:400}]}});
 assert.equal(r.providerCategory,'route-unavailable-reported');assert.equal(r.providerCode,400);
 assert.ok(r.knownProviderCodes.includes('COULD_NOT_FIND_ANY_ROUTE'));
 assert.ok(r.errorFieldShapes.some(s=>s.path==='error.details[].message'));
});
test('unknown errors retain safe vocabulary and fingerprint without arbitrary text',()=>{
 const secret='SecretOpaqueCredential0123456789';const r=errorEvidence({error:{message:'upstream quote failed '+secret,requestId:secret},requestId:secret});
 const raw=JSON.stringify(r);assert.ok(!raw.includes(secret));assert.ok(!raw.includes('requestId'));
 assert.equal(r.providerCategory,'quote-generation-failure-reported');assert.ok(r.diagnosticTerms.includes('upstream'));
 assert.match(r.messageFingerprint,/^[a-f0-9]{64}$/);assert.equal(r.messageFingerprint,errorEvidence({error:{message:'upstream quote failed '+secret}}).messageFingerprint);
});
test('unknown codes and arbitrary object keys are never exported',()=>{
 const r=errorEvidence({error:{code:'PRIVATE_AUTH_VALUE',unrecognized:'something-private'}});
 assert.deepEqual(r.knownProviderCodes,[]);assert.ok(!JSON.stringify(r).includes('PRIVATE_AUTH_VALUE'));assert.ok(!JSON.stringify(r).includes('unrecognized'));
});
test('depth, array length and message length are bounded',()=>{
 const r=errorEvidence({error:{details:Array(100).fill({message:'x'.repeat(900)})}});
 assert.equal(r.extractionTruncated,true);assert.ok(r.errorFieldShapes.length<=32);assert.ok(JSON.stringify(r).length<5000);
 const deep=errorEvidence({error:{error:{error:{error:{message:'no route found'}}}}});
 assert.equal(deep.extractionTruncated,true);assert.equal(deep.providerCategory,'unclassified-provider-rejection');
});
test('successful HTTP envelope with a provider error uses the same diagnostics',()=>{
 const r=parseQuote({error:{message:'TOKEN_NOT_TRADABLE'}},'x','y','1');
 assert.equal(r.status,'provider-error');assert.equal(r.providerCategory,'token-unsupported-reported');
});
