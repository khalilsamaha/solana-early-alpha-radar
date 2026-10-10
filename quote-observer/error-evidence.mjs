// Bounded structural diagnostics. No arbitrary provider text is exported.
import {createHash} from 'node:crypto';
const KEYS=['error','errors','errorMessage','message','detail','details','reason','errorCode','code'];
const TERMS=new Set(('amount invalid too small large insufficient liquidity route routes routing no not found available unavailable token unsupported tradable supported sell buy quote failed failure rejected request input output mint account balance simulation program instruction custom error market pool bonding curve complete completed migrated migration timeout expired internal upstream service calculate compute overflow underflow disabled frozen transfer fee fees minimum maximum slippage limit exceeded').split(' '));
const CODES=new Set(['NO_ROUTES_FOUND','COULD_NOT_FIND_ANY_ROUTE','TOKEN_NOT_TRADABLE','NOT_SUPPORTED','AMOUNT_TOO_SMALL','INSUFFICIENT_LIQUIDITY','INVALID_AMOUNT','MARKET_NOT_FOUND']);
export function errorEvidence(body){
  if(!body||typeof body!=='object'||Array.isArray(body))return {errorBodyStatus:'unrecognized'};
  const texts=[],shapes=[],codes=[];let nodes=0,truncated=false;
  function visit(value,path,depth){
    if(++nodes>32||depth>3){truncated=true;return;}
    const type=value===null?'null':Array.isArray(value)?'array':typeof value;
    shapes.push({path,type});
    if(type==='string'){
      if(value.length>512)truncated=true;
      texts.push(value.slice(0,512));
      if(CODES.has(value))codes.push(value);
    }else if(type==='number'&&Number.isSafeInteger(value)&&/(?:^|\.)(?:code|errorCode)$/.test(path))codes.push(value);
    else if(type==='array'){
      if(value.length>4)truncated=true;
      value.slice(0,4).forEach(v=>visit(v,path+'[]',depth+1));
    }else if(type==='object')for(const key of KEYS)if(Object.hasOwn(value,key))visit(value[key],path+'.'+key,depth+1);
  }
  for(const key of KEYS)if(Object.hasOwn(body,key))visit(body[key],key,0);
  const msg=texts.join(' ').replace(/_/g,' ').slice(0,8192);
  const categories=[
    [/no routes? found|could not find.*route|route.*not found|no.*route.*available/i,'route-unavailable-reported'],
    [/insufficient.*liquidity|not enough.*liquidity/i,'insufficient-liquidity-reported'],
    [/amount.*(invalid|too|small|large)|invalid.*amount/i,'amount-rejected-reported'],
    [/token.*(unsupported|not supported|not tradable)|unsupported.*token/i,'token-unsupported-reported'],
    [/slippage.*(exceeded|limit)|exceeded.*slippage/i,'slippage-rejection-reported'],
    [/simulation.*fail|fail.*simulation/i,'simulation-failure-reported'],
    [/bonding.*curve.*(complete|migrat)|pool.*migrat/i,'pool-transition-reported'],
    [/(fail|unable).*quote|quote.*(fail|reject)/i,'quote-generation-failure-reported']
  ];
  return {errorBodyStatus:'json',errorEvidenceVersion:'structured-errors-v2',
    providerCode:codes.find(c=>typeof c==='number')??null,knownProviderCodes:[...new Set(codes.filter(c=>typeof c==='string'))],
    providerCategory:categories.find(([re])=>re.test(msg))?.[1]||'unclassified-provider-rejection',
    presentErrorFields:KEYS.filter(k=>Object.hasOwn(body,k)),errorFieldShapes:shapes.slice(0,32),
    diagnosticTerms:[...new Set((msg.toLowerCase().match(/[a-z]+/g)||[]).filter(w=>TERMS.has(w)))].slice(0,32),
    messageFingerprint:texts.length?createHash('sha256').update(texts.join('\n')).digest('hex'):null,
    extractionTruncated:truncated,
    interpretation:'Provider text classification only; not verified root cause. Arbitrary text omitted.'};
}
