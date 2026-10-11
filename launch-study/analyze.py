"""As-of launch context and original-pool outcomes. All contrasts are exploratory."""
import bisect, collections, hashlib, json, math, statistics
from pathlib import Path

PROTOCOL=json.loads(Path(__file__).with_name('protocol.json').read_text())
PROTOCOL_HASH=hashlib.sha256(json.dumps(PROTOCOL,sort_keys=True,separators=(',',':')).encode()).hexdigest()
HORIZONS=PROTOCOL['horizonsMs']
ALIASES={'30s':'30s','1m':'60s','2m':'120s','5m':'300s','60s':'60s','120s':'120s','300s':'300s'}

def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def timestamp(x):return type(x) is int and 0<x<2**53
def text(x,limit=180):return isinstance(x,str) and 0<len(x)<=limit

def distribution(values):
    values=sorted(values);n=len(values)
    def quantile(p):
        if not n:return None
        k=(n-1)*p;i=math.floor(k);j=math.ceil(k)
        return values[i]+(values[j]-values[i])*(k-i)
    return {'observed':n,'meanPct':statistics.mean(values) if n else None,'medianPct':statistics.median(values) if n else None,
        'p05Pct':quantile(.05),'p95Pct':quantile(.95),'positive':sum(x>0 for x in values),'lossAtLeast50':sum(x<=-50 for x in values),
        'meanWithoutBestPct':statistics.mean(values[:-1]) if n>1 else None}

def entry_record(item):
    r=item['data'];kind=item['kind'];cohort=r.get('cohort')
    expected='fast30-shadow-1' if kind=='fast-shadow-entries' else 'research-0.2.9'
    if kind not in ('fast-shadow-entries','research-entries') or r.get('version')!=expected:return None,'unsupported-version'
    if (kind=='fast-shadow-entries' and cohort!='fast30-shadow') or (kind=='research-entries' and cohort not in ('baseline','early-activity')):return None,'unsupported-cohort'
    if not text(r.get('id')) or r['id']!=item['eventId'] or not timestamp(r.get('at')) or r['at']!=item['eventAt'] or not text(r.get('mint'),44):return None,'invalid-entry-identity'
    c=r.get('candidate') or {};pool=r.get('pairAddress');price=r.get('priceUsd')
    if not text(pool,88) or not finite(price) or price<=0:return None,'invalid-entry-price-or-pool'
    if c and any(c.get(k) not in (None,r.get(k)) for k in ('mint','pairAddress','priceUsd')):return None,'contradictory-entry-candidate'
    liquidity=r.get('liquidityUsd') if kind=='fast-shadow-entries' else c.get('liquidityUsd')
    liquidity=liquidity if finite(liquidity) and liquidity>=0 else None
    follow=r.get('followup') or {}
    return {'sourceSeq':item['seq'],'entryId':r['id'],'entryKind':kind,'cohort':cohort,'mint':r['mint'],'entryAt':r['at'],
        'pairAddress':pool,'priceUsd':price,'liquidityUsd':liquidity,
        'liquidityGroup':'unknown' if liquidity is None else 'at-least-5000' if liquidity>=5000 else 'below-5000',
        'followupPolicy':follow.get('policy','not-recorded') if kind=='fast-shadow-entries' else 'research-original-pool',
        'followupAdmitted':follow.get('admitted') if kind=='fast-shadow-entries' else None},None

def outcome(e,h,item,cutoff):
    due=e['entryAt']+HORIZONS[h];deadline=due+PROTOCOL['checkpointToleranceMs']
    base={'state':'pending' if cutoff<=deadline else 'overdue','grossPriceChangePct':None,'dueAt':due,'sampleAt':None,'recordedAt':None}
    if not item:return base
    r=item['data'];base.update(recordedAt=r.get('at'),sampleAt=r.get('sampleAt'),reasonCode=r.get('reasonCode'))
    expected_kind='fast-shadow-outcomes' if e['entryKind']=='fast-shadow-entries' else 'research-outcomes'
    valid=(item['kind']==expected_kind and r.get('id')==item['eventId']==e['entryId']+':'+str(r.get('horizon')) and
        r.get('entryId')==e['entryId'] and r.get('mint')==e['mint'] and r.get('entryAt')==e['entryAt'] and
        timestamp(r.get('at')) and r['at']==item['eventAt'] and e['entryAt']<=r['at']<=cutoff and ALIASES.get(r.get('horizon'))==h)
    if e['entryKind']=='research-entries':valid=valid and r.get('cohort')==e['cohort'] and r.get('entryPool')==e['pairAddress']
    else:valid=valid and r.get('pairAddress')==e['pairAddress']
    if not valid:return {**base,'state':'invalid'}
    if r.get('status')=='missing':return {**base,'state':'missing'}
    valid=(r.get('status')=='observed' and timestamp(r.get('sampleAt')) and due<=r['sampleAt']<=r['at']<=deadline and
        finite(r.get('priceUsd')) and r['priceUsd']>0 and finite(r.get('returnPct')) and
        math.isclose(r['returnPct'],(r['priceUsd']/e['priceUsd']-1)*100,rel_tol=1e-9,abs_tol=1e-8))
    if not valid:return {**base,'state':'invalid'}
    if r.get('coverage')=='gapped':return {**base,'state':'gapped'}
    if r.get('coverage')!='sampled':return {**base,'state':'invalid'}
    return {**base,'state':'observed','grossPriceChangePct':r['returnPct']}

def indexes(contexts):
    seen=set();groups={'traderReported':collections.defaultdict(list),'metadataUriSha256':collections.defaultdict(list)}
    for r in contexts:
        if not text(r.get('mint'),44) or not timestamp(r.get('availableAt')) or r['mint'] in seen:raise ValueError('Duplicate/invalid launch context')
        seen.add(r['mint'])
        for key,group in groups.items():
            if r.get(key) is not None:
                if not text(r[key],88):raise ValueError('Invalid context field')
                group[r[key]].append(r['availableAt'])
    return {key:{actor:sorted(times) for actor,times in group.items()} for key,group in groups.items()}

def launch_features(e,launch,index,capture):
    result={'state':'no-retained-launch-record','availableAt':None,'receiptToSignalMs':None,'traderReported':None,'creatorReported':None,
        'priorReceivedTraderLaunches24h':None,'priorReceivedSameUriHash24h':None,'traderGroup':'unknown','uriHashGroup':'unknown',
        'reportedFields':None,'lookbackCalendarSpanMs':None,'continuousFeedCoverageProven':False}
    if not launch:return result
    at=launch.get('availableAt')
    if launch.get('version')!='launch-registry-1' or launch.get('mint')!=e['mint'] or not timestamp(at) or at!=launch.get('receivedAt') or not isinstance(launch.get('fields'),dict):return {**result,'state':'invalid-launch-record'}
    result['availableAt']=at
    if at>e['entryAt']:return {**result,'state':'launch-received-after-signal'}
    fields=launch['fields'];result.update(state='available-before-signal',receiptToSignalMs=e['entryAt']-at,
        traderReported=fields.get('traderReported'),creatorReported=fields.get('creatorReported'),reportedFields=fields)
    lower=e['entryAt']-PROTOCOL['lookbackMs']
    earliest=max(capture['registration']['registeredAt'],capture.get('earliestRetainedReceiptAt') or e['entryAt'],lower)
    result['lookbackCalendarSpanMs']=max(0,e['entryAt']-earliest)
    for field,count_key,group_key in [('traderReported','priorReceivedTraderLaunches24h','traderGroup'),('metadataUriSha256','priorReceivedSameUriHash24h','uriHashGroup')]:
        actor=fields.get(field)
        if actor is None:continue
        times=index[field].get(actor,[])
        n=bisect.bisect_left(times,e['entryAt'])-bisect.bisect_left(times,lower)
        # The registry has one row per mint; omit this mint even if its launch predates the decision.
        if lower<=at<e['entryAt']:n-=1
        if n<0:raise ValueError('Context missing current mint; cannot compute prior counts')
        result[count_key]=n;result[group_key]='one-or-more-other-received-launches' if n else 'no-other-received-launches'
    return result

def summarize(rows):
    hs={}
    for h in HORIZONS:
        counts=collections.Counter(r['outcomes'][h]['state'] for r in rows)
        values=[r['outcomes'][h]['grossPriceChangePct'] for r in rows if r['outcomes'][h]['state']=='observed']
        hs[h]={'states':dict(counts),'grossPriceChange':distribution(values)}
    traders={r['launch']['traderReported'] for r in rows if r['launch']['traderReported']}
    return {'entries':len(rows),'distinctMints':len({r['mint'] for r in rows}),'distinctReportedTraders':len(traders),
        'traderUnknownEntries':sum(r['launch']['traderReported'] is None for r in rows),
        'launchStates':dict(collections.Counter(r['launch']['state'] for r in rows)),'horizons':hs}

def analyze(capture):
    if capture.get('format')!='launch-study-capture-1' or not text(capture.get('sourceIdentity')):raise ValueError('Unsupported capture or missing source identity')
    cutoff=capture['cutoffAt'];start=capture['windowStartAt']
    if not timestamp(cutoff) or not timestamp(start) or start>cutoff:raise ValueError('Invalid capture window')
    entries=capture['entries'];outcomes=capture['outcomes'];launches=capture['matchedMintLaunchRecords'];contexts=capture['relatedLaunchContext']
    if len(entries)>6000 or len(outcomes)>24000 or len(launches)>6000 or len(contexts)>100000:raise ValueError('Analysis cap reached')
    by_launch={r['mint']:r for r in launches}
    if len(by_launch)!=len(launches):raise ValueError('Duplicate mint launch')
    registration=capture.get('registration',{})
    if registration.get('version')!='launch-registry-1' or not timestamp(registration.get('registeredAt')) or not registration['registeredAt']<=start:raise ValueError('Invalid registration window')
    if capture.get('contextWindowStartAt',start)>start-PROTOCOL['lookbackMs']:raise ValueError('Incomplete context query window')
    idx=indexes(contexts);context_by_mint={r['mint']:r for r in contexts}
    for r in contexts:
        if not capture['contextWindowStartAt']<=r['availableAt']<=cutoff:raise ValueError('Context outside capture window')
    for launch in launches:
        at=launch.get('availableAt');fields=launch.get('fields',{})
        if timestamp(at) and capture['contextWindowStartAt']<=at<=cutoff and any(fields.get(k) is not None for k in ('traderReported','metadataUriSha256')):
            expected={'mint':launch['mint'],'availableAt':at,**{k:fields.get(k) for k in ('traderReported','metadataUriSha256')}}
            if context_by_mint.get(launch['mint'])!=expected:raise ValueError('Missing or inconsistent current-mint context')
    by_outcome={};seen_seq=set()
    for item in outcomes:
        if item['seq'] in seen_seq:raise ValueError('Duplicate outcome sequence')
        seen_seq.add(item['seq']);r=item['data'];key=(item['kind'],r.get('entryId'),ALIASES.get(r.get('horizon')))
        if key in by_outcome:raise ValueError('Duplicate entry horizon')
        by_outcome[key]=item
    rows=[];excluded=[];seen=set();seen_seq=set()
    for item in entries:
        if item['seq'] in seen_seq or (item['kind'],item['eventId']) in seen:raise ValueError('Duplicate entry identity')
        seen.add((item['kind'],item['eventId']));seen_seq.add(item['seq'])
        e,error=entry_record(item)
        if error:excluded.append({'sourceSeq':item['seq'],'reason':error});continue
        if not start<=e['entryAt']<=cutoff:raise ValueError('Entry outside capture window')
        e['launch']=launch_features(e,by_launch.get(e['mint']),idx,capture)
        kind='fast-shadow-outcomes' if e['entryKind']=='fast-shadow-entries' else 'research-outcomes'
        e['outcomes']={h:outcome(e,h,by_outcome.get((kind,e['entryId'],h)),cutoff) for h in HORIZONS}
        rows.append(e)
    cohorts=collections.defaultdict(list);groups=collections.defaultdict(list);time_blocks=collections.defaultdict(list)
    for r in rows:
        cohorts[r['cohort']].append(r)
        for contrast in ('traderGroup','uriHashGroup'):
            group=(r['cohort'],r['followupPolicy'],str(r['followupAdmitted']),r['liquidityGroup'],contrast,r['launch'][contrast])
            groups[group].append(r)
        time_blocks[(r['cohort'],r['entryAt']//3600000*3600000)].append(r)
    return {'version':PROTOCOL['id'],'mode':PROTOCOL['mode'],'protocol':PROTOCOL,'protocolSha256':PROTOCOL_HASH,
        'sourceEntries':len(entries),'analyzedEntries':len(rows),'excludedEntries':excluded,
        'cohorts':{k:summarize(v) for k,v in sorted(cohorts.items())},
        'contrasts':[{'cohort':k[0],'followupPolicy':k[1],'followupAdmitted':k[2],'liquidityGroup':k[3],'contrast':k[4],'group':k[5],**summarize(v)} for k,v in sorted(groups.items())],
        'hourBlocks':[{'cohort':k[0],'blockStartAt':k[1],**summarize(v)} for k,v in sorted(time_blocks.items())],
        'cases':rows,
        'limitations':['All contrasts are exploratory, not a registered prospective trading strategy or causal effect.',
            'Only recorded research entries after launch-registry registration are studied; not returns for every launched token.',
            'Reported creation trader is not a verified creator, owner, insider or organic participant.',
            'Prior counts are strictly earlier retained receipts of other mints; zero is not first-ever activity. Same-timestamp events are excluded.',
            'Calendar lookback does not prove continuous feed coverage; downtime, retention and cap losses cannot be reconstructed.',
            'Metadata URI hash equality is not identical-content verification or evidence of fraud.',
            'Reported creation quantities retain provider units; no reserve ratio, inferred decimals or executable price is calculated.',
            'Original-pool observed gross changes exclude fees/fills. Missing, gapped, invalid, pending and overdue outcomes remain in denominators.',
            'Repeated mints/traders and overlapping cohorts are dependent. Group differences and best-winner removal are descriptive only.',
            'Historical replay remains exploratory; changing the report timestamp does not make old evidence forward validation.']}
