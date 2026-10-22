"""Offline launch/observer joins. No network, source writes, interpolation or fills."""
import collections
import copy
import math
from analyze import analyze, distribution, finite, timestamp, text

VERSION = 'launch-quote-join-1'
USDC = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
COHORTS = ('baseline', 'early-activity', 'fast30-shadow')
OFFSETS = (0, 30000, 60000, 120000)
IDENTITY_FIELDS = ('seq', 'cohort', 'entryId', 'eventId', 'mint', 'signalAt', 'originalPool', 'entryPriceUsd', 'detectedAt', 'samplingPolicy')


def atomic(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value)>20:
        raise ValueError('Invalid atomic amount')
    n = int(value)
    if not 0<n<2**64:
        raise ValueError('Invalid atomic amount')
    return n


def clock(row, after, cutoff):
    return timestamp(row.get('startedAt')) and timestamp(row.get('receivedAt')) and after<=row['startedAt']<=row['receivedAt']<=cutoff


def route(row, signal):
    plan = row.get('routePlan')
    if not isinstance(plan, list) or row.get('routePlanTruncated') is not False:
        return {'state':'unavailable-or-truncated', 'tokenPools':None, 'originalPoolPresent':None}
    if len(plan)>64 or any(not isinstance(p,dict) for p in plan):
        return {'state':'invalid-route', 'tokenPools':None, 'originalPoolPresent':None}
    pools = sorted({p['pool'] for p in plan if signal['mint'] in (p.get('inputMint'),p.get('outputMint')) and text(p.get('pool'),88)})
    if not pools:
        return {'state':'unavailable', 'tokenPools':None, 'originalPoolPresent':None}
    return {'state':'reported', 'tokenPools':pools, 'originalPoolPresent':signal['originalPool'] in pools}


def probe_case(probe, signal, cutoff):
    """Validate quantities and clocks before computing any quoted change."""
    base = {'buy':{'state':'not-recorded'}, 'exits':{}, 'latestProbeState':None}
    if probe is None:
        base['buy']['state']='admitted-probe-not-exported'
        base['exits']={str(h):{'state':'admitted-probe-not-exported','quotedChangePct':None} for h in OFFSETS}
        return base
    if any(probe.get('signal',{}).get(k)!=signal.get(k) for k in IDENTITY_FIELDS) or probe.get('samplingPolicy')!=signal.get('samplingPolicy'):
        base['buy']['state']='probe-identity-mismatch'
        base['exits']={str(h):{'state':'probe-identity-mismatch','quotedChangePct':None} for h in OFFSETS}
        return base
    base['latestProbeState']=probe.get('state')  # Export-time state, not reconstructed historical state.
    obs=probe.get('observations')
    if not isinstance(obs,list) or len(obs)>5 or any(not isinstance(o,dict) or o.get('leg') not in ('buy','sell') for o in obs):
        raise ValueError('Invalid observation envelope')
    buys=[o for o in obs if o['leg']=='buy']
    if len(buys)>1:raise ValueError('Duplicate buy')
    buy=buys[0] if buys else None
    sells={}
    for o in obs:
        if o['leg']!='sell':continue
        h=o.get('targetOffsetMs')
        if type(h) is not int or h not in OFFSETS or h in sells:raise ValueError('Duplicate/unsupported exit')
        sells[h]=o
    valid=False;quantity=None;input_amount=None
    if buy:
        state='invalid-buy-evidence'
        if timestamp(buy.get('receivedAt')) and buy['receivedAt']>cutoff:state='after-cutoff'
        elif clock(buy,signal['detectedAt'],cutoff):
            if buy.get('status')!='quoted':state='buy-quote-failed'
            else:
                try:
                    valid=(buy.get('inputMint')==USDC==probe.get('baseMint') and buy.get('outputMint')==signal['mint']==probe.get('mint')
                        and atomic(buy.get('inAmount'))==atomic(probe.get('inputAtomic'))==10000000 and buy.get('transactionRequested') is False and buy.get('executionVerified') is False)
                    quantity=atomic(buy.get('outAmount'));input_amount=atomic(buy.get('inAmount'))
                except (TypeError,ValueError):valid=False
                if valid:state='validated-buy-quote'
        base['buy']={'state':state,'status':buy.get('status'),'requestAt':buy.get('startedAt'),'responseAt':buy.get('receivedAt'),
            'inputAtomic':str(input_amount) if valid else None,'tokenQuantityAtomic':str(quantity) if valid else None,
            'signalToRequestMs':buy['startedAt']-signal['signalAt'] if valid else None,
            'signalToResponseMs':buy['receivedAt']-signal['signalAt'] if valid else None,
            'route':route(buy,signal) if valid else None}
    finished=probe.get('finishedAt')
    known_finished=timestamp(finished) and finished<=cutoff
    for h in OFFSETS:
        o=sells.get(h);result={'state':'not-recorded','quotedChangePct':None,'targetOffsetMs':h,'targetClock':'buy-response'}
        if not valid:
            result['state']='no-validated-buy-quote'
        else:
            due=buy['receivedAt']+h
            if h==0:due=max(due,buy['startedAt']+10000)
            latest=due+23000  # observer scheduling allowance 15s + request timeout 8s
            result.update(scheduledAt=buy['receivedAt']+h)
            if o is None:
                result['state']='unfinished-at-cutoff' if cutoff<=latest else 'incomplete-unrecorded' if known_finished else 'overdue-unrecorded'
            elif timestamp(o.get('receivedAt')) and o['receivedAt']>cutoff:
                result['state']='after-cutoff'
            elif o.get('status')=='skipped' and not timestamp(o.get('receivedAt')):
                result['state']='not-sampled' if known_finished else 'skip-time-unavailable'
                result['reason']=o.get('reason')
            elif not clock(o,buy['receivedAt'],cutoff):result['state']='invalid-exit-clock'
            elif o.get('status')!='quoted':
                result.update(state='interrupted' if o.get('status')=='interrupted' else 'sell-quote-failed',status=o.get('status'),providerCategory=o.get('providerCategory'))
            else:
                try:
                    good=(o.get('inputMint')==signal['mint'] and o.get('outputMint')==USDC and atomic(o.get('inAmount'))==quantity
                        and o['startedAt']>=buy['receivedAt']+h and o.get('transactionRequested') is False and o.get('executionVerified') is False)
                    proceeds=atomic(o.get('outAmount'))
                    if not good:raise ValueError('Invalid exit')
                    change=(proceeds-input_amount)/input_amount*100
                    stored=o.get('quotedUsdcChangePct')
                    if not finite(stored) or not math.isclose(change,stored,rel_tol=0,abs_tol=.000101):raise ValueError('Return mismatch')
                    rr=route(o,signal);br=base['buy']['route']
                    result.update(state='validated-sell-quote',quotedChangePct=change,inputAtomic=str(quantity),outputAtomic=str(proceeds),
                        requestAt=o['startedAt'],responseAt=o['receivedAt'],signalToResponseMs=o['receivedAt']-signal['signalAt'],
                        scheduleDelayMs=o['startedAt']-buy['receivedAt']-h,lateBeyond5s=o['startedAt']-buy['receivedAt']-h>5000,responseBeyond8s=o['receivedAt']-o['startedAt']>8000,
                        route=rr,tokenRouteChanged=rr['tokenPools']!=br['tokenPools'] if rr['tokenPools'] is not None and br['tokenPools'] is not None else None)
                except (TypeError,ValueError):result['state']='invalid-exit-quantity-mint-or-return'
        base['exits'][str(h)]=result
    return base


def returns(values):
    return {**distribution(values),'worstPct':min(values) if values else None,'bestPct':max(values) if values else None}


def summary(rows):
    result={'entries':len(rows),'observerStates':dict(collections.Counter(r['observer']['state'] for r in rows)),
        'decisions':dict(collections.Counter(r['observer'].get('decision') or 'unavailable' for r in rows)),
        'admitted':sum(r['observer'].get('decision')=='admitted' for r in rows),
        'buyStates':dict(collections.Counter(r['quote']['buy']['state'] for r in rows)),'horizons':{}}
    for h in OFFSETS:
        exits=[r['quote']['exits'][str(h)] for r in rows]
        paired=[x for x in exits if x.get('paperChangePct') is not None and x.get('quotedChangePct') is not None]
        result['horizons'][str(h)]={'states':dict(collections.Counter(x['state'] for x in exits)),
            'quotedChange':returns([x['quotedChangePct'] for x in exits if x.get('quotedChangePct') is not None]),
            'onTimeQuotedChange':returns([x['quotedChangePct'] for x in exits if x.get('quotedChangePct') is not None and not x.get('lateBeyond5s') and not x.get('responseBeyond8s')]) if h else None,
            'paired':len(paired),'paperChangeSameCases':distribution([x['paperChangePct'] for x in paired]),
            'oppositeSigns':sum(x['paperChangePct']*x['quotedChangePct']<0 for x in paired),
            'lateBeyond5s':sum(x.get('lateBeyond5s',False) for x in exits),
            'originalPoolAbsent':sum(x.get('route',{}).get('originalPoolPresent') is False for x in exits)}
    return result


def join(capture,quotes):
    if quotes.get('format')!='quote-observer-report-0.2.0':raise ValueError('Unsupported quote export')
    if not capture.get('sourceIdentity') or quotes.get('sourceIdentity')!=capture['sourceIdentity']:raise ValueError('Source identity mismatch')
    qend=quotes.get('capturedAt');qstart=quotes.get('windowStartAt')
    if not timestamp(qend) or not timestamp(qstart) or qstart>qend:raise ValueError('Invalid quote window')
    original=analyze(capture)  # Never trust a supplied derived analysis.
    start=max(capture['windowStartAt'],qstart);end=min(capture['cutoffAt'],qend)
    if start>end:raise ValueError('No overlapping report windows')
    c=copy.copy(capture);c.update(windowStartAt=start,cutoffAt=end)
    c['entries']=[r for r in capture['entries'] if start<=r['eventAt']<=end]
    c['outcomes']=[r for r in capture['outcomes'] if r['eventAt']<=end]
    c['relatedLaunchContext']=[r for r in capture['relatedLaunchContext'] if r['availableAt']<=end]
    analysis=analyze(c);entries=analysis['cases']
    by_id={e['entryId']:e for e in entries};by_tuple=collections.defaultdict(list)
    if len(by_id)!=len(entries):raise ValueError('Duplicate study entry IDs')
    for e in entries:by_tuple[(e['cohort'],e['mint'],e['entryAt'])].append(e)
    if any(len(v)>1 for v in by_tuple.values()):raise ValueError('Ambiguous study identity')
    ss=quotes.get('signals');ps=quotes.get('probes')
    if not isinstance(ss,list) or not isinstance(ps,list) or len(ss)>20000 or len(ps)>1000:raise ValueError('Quote record cap/schema')
    signals={};probes={}
    for s in ss:
        seq=s.get('seq')
        if type(seq) is not int or seq<=0 or seq in signals:raise ValueError('Duplicate/invalid signal sequence')
        signals[seq]=s
    for p in ps:
        seq=p.get('signal',{}).get('seq')
        if type(seq) is not int or seq<=0 or seq in probes:raise ValueError('Duplicate/invalid probe sequence')
        probes[seq]=p
    matches={};unmatched=[]
    for seq,s in signals.items():
        e=by_id.get(s.get('entryId')) if s.get('cohort')!='baseline' else next(iter(by_tuple.get(('baseline',s.get('mint'),s.get('signalAt')),[])),None)
        reason='no-study-entry-in-common-window'
        if s.get('cohort') not in COHORTS:reason='other-or-invalid-cohort'
        elif e:
            good=(s.get('cohort')==e['cohort'] and s.get('mint')==e['mint'] and s.get('signalAt')==e['entryAt']
                and s.get('originalPool')==e['pairAddress'] and s.get('entryPriceUsd')==e['priceUsd'] and s.get('eventId')==s.get('entryId'))
            if e['cohort']=='baseline':
                parts=str(s.get('eventId')).split(':')
                good=good and len(parts)==3 and parts[0]==e['mint'] and parts[1]==str(e['entryAt']) and parts[2].isdigit() and int(parts[2])>0
            else:good=good and s['seq']==e['sourceSeq']
            reason='matched' if good else 'entry-identity-mismatch'
            if e['entryId'] in matches:raise ValueError('Multiple observer signals for one study entry')
            matches[e['entryId']]=(s,reason)
        unmatched.append({'seq':seq,'state':reason}) if reason!='matched' else None
    rows=[]
    for e in entries:
        m=matches.get(e['entryId']);state='no-observer-signal-in-export';decision=None;s=None
        if m:
            s,state=m
            if state=='matched':
                if not timestamp(s.get('detectedAt')) or not e['entryAt']<=s['detectedAt']<=qend:state='invalid-observer-clock'
                elif s['detectedAt']>end:state='observer-detected-after-cutoff'
                elif not text(s.get('decision'),80):state='invalid-observer-decision'
                else:decision=s['decision']
        obs={'state':state,'decision':decision,'seq':s.get('seq') if s else None,'samplingPolicy':s.get('samplingPolicy') if s else None,
            'joinMethod':'baseline-cohort-mint-time-pool-price' if e['cohort']=='baseline' else 'entry-id-and-source-sequence'}
        quote=probe_case(probes.get(s['seq']),s,end) if decision=='admitted' else {
            'buy':{'state':'not-admitted' if decision else 'observer-unavailable'},
            'exits':{str(h):{'state':'not-admitted' if decision else 'observer-unavailable','quotedChangePct':None} for h in OFFSETS}}
        for h in OFFSETS:
            x=quote['exits'][str(h)];po=e['outcomes'].get(str(h//1000)+'s')
            x['paperState']=po['state'] if po else 'no-corresponding-checkpoint'
            x['paperChangePct']=po['grossPriceChangePct'] if po else None
            x['paperSampleAt']=po['sampleAt'] if po else None
            if x.get('quotedChangePct') is not None and x['paperChangePct'] is not None:
                x['paperMinusQuoteReceiptMs']=po['sampleAt']-x['responseAt']
                x['differencePercentagePoints']=x['paperChangePct']-x['quotedChangePct']
        rows.append({**e,'observer':obs,'quote':quote})
    groups=collections.defaultdict(list);contrasts=collections.defaultdict(list)
    for r in rows:
        policy=r['observer'].get('samplingPolicy') or 'unknown'
        groups[(r['cohort'],policy)].append(r)
        for k in ('traderGroup','uriHashGroup'):
            contrasts[(r['cohort'],policy,r['followupPolicy'],str(r['followupAdmitted']),r['liquidityGroup'],k,r['launch'][k])].append(r)
    export_groups=collections.defaultdict(list);unlinked=[]
    for seq,p in probes.items():
        s=signals.get(seq)
        if not s or s.get('decision')!='admitted' or s.get('cohort') not in COHORTS or not timestamp(s.get('signalAt')) or not timestamp(s.get('detectedAt')) or not s['signalAt']<=s['detectedAt']<=qend:
            unlinked.append({'seq':seq,'state':'no-valid-admission-record'});continue
        export_groups[(s['cohort'],s.get('samplingPolicy') or 'unknown')].append({'observer':{'state':'export-admission','decision':'admitted'},'quote':probe_case(p,s,qend)})
    return {'version':VERSION,'mode':'exploratory-descriptive','sourceIdentity':capture['sourceIdentity'],
        'commonWindow':{'startAt':start,'cutoffAt':end,'studyCutoffAt':capture['cutoffAt'],'quoteCutoffAt':qend},
        'studyEntries':original['analyzedEntries'],'commonWindowEntries':len(rows),'excludedInvalidStudyEntries':analysis['excludedEntries'],
        'studyEntriesOutsideCommonWindow':[{'entryId':e['entryId'],'reason':'before-quote-export-window' if e['entryAt']<start else 'after-common-cutoff'} for e in original['cases'] if not start<=e['entryAt']<=end],
        'matchedObserverDecisions':sum(r['observer']['state']=='matched' for r in rows),'admitted':sum(r['observer'].get('decision')=='admitted' for r in rows),
        'comparisonProtocol':{'primaryOffsetMs':30000,'comparatorOffsetsMs':[60000,120000],'clock':'buy-response','hypotheticalInputUsdc':'10','maximumScheduleDelayMs':5000,'maximumResponseMs':8000,'mode':'descriptive-no-strategy-promotion'},
        'groups':[{'cohort':k[0],'samplingPolicy':k[1],**summary(v)} for k,v in sorted(groups.items())],
        'launchContrasts':[{'cohort':k[0],'samplingPolicy':k[1],'followupPolicy':k[2],'followupAdmitted':k[3],'liquidityGroup':k[4],'contrast':k[5],'group':k[6],**summary(v)} for k,v in sorted(contrasts.items())],
        'wholeQuoteExportGroups':[{'cohort':k[0],'samplingPolicy':k[1],**summary(v)} for k,v in sorted(export_groups.items())],
        'unmatchedObserverSignals':unmatched,'unlinkedQuoteProbes':unlinked,'cases':rows,
        'limitations':['Matched study and whole quote export have different denominators and clocks; never mix their summaries.',
            'Quotes are not fills or net profit. Amount arithmetic is recomputed; no fees are added or subtracted by this report.',
            'Unquoted signals have no quoted return. Sampling is capacity-limited and non-random.',
            'Baseline research and alert IDs differ; baseline joins require unique cohort/mint/time/pool/price and valid alert identity.',
            'Only received observations available by the common cutoff contribute to matched quoted outcomes.',
            'Probe state is export-time metadata. Unstamped skips need a known completion time or stay unavailable.',
            'Paper checkpoints use signal time; quote exits use buy-response time. Differences are not measured slippage.',
            'The zero-offset sell is delayed by request spacing. Thirty seconds is the primary comparison; later horizons remain comparators.',
            'Reported route availability does not establish execution, depth or safety. Truncated/absent routes stay unknown.',
            'Launch contrasts remain exploratory; historical replay does not create forward validation or promote trading rules.']}
