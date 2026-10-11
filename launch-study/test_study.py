import copy
import gzip
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analyze import analyze, distribution
from capture import capture
from report import publish, read_capture

T=1800000000000
M='A'*32
P='B'*32
TRADER='C'*32


def launch(mint=M, at=T-10000, trader=TRADER, uri='d'*64):
    return {'version':'launch-registry-1','mint':mint,'receivedAt':at,'availableAt':at,
        'fields':{'traderReported':trader,'creatorReported':None,'metadataUriSha256':uri,'initialBuyReported':'0','decimalsReported':None}}


def entry(cohort='fast30-shadow', at=T, mint=M, seq=1):
    kind='fast-shadow-entries' if cohort=='fast30-shadow' else 'research-entries'
    version='fast30-shadow-1' if cohort=='fast30-shadow' else 'research-0.2.9'
    r={'id':f'{version}:{cohort}:{mint}:{at}','version':version,'cohort':cohort,'mint':mint,'at':at,'priceUsd':2,'pairAddress':P,
       'followup':{'policy':'fast-followup-1','admitted':True},'liquidityUsd':10000}
    if cohort!='fast30-shadow':r['candidate']={'mint':mint,'pairAddress':P,'priceUsd':2,'liquidityUsd':10000}
    return {'seq':seq,'kind':kind,'eventId':r['id'],'eventAt':at,'data':r}


def outcome(e,h='30s',ms=30000,seq=100,status='observed',coverage='sampled',price=3):
    r=e['data'];fast=e['kind']=='fast-shadow-entries';at=r['at']+ms
    d={'id':r['id']+':'+h,'entryId':r['id'],'mint':r['mint'],'cohort':r['cohort'],'entryAt':r['at'],'horizon':h,
       'at':at,'sampleAt':at,'status':status,'coverage':coverage,'priceUsd':price,'returnPct':(price/r['priceUsd']-1)*100}
    d['pairAddress' if fast else 'entryPool']=r['pairAddress']
    return {'seq':seq,'kind':'fast-shadow-outcomes' if fast else 'research-outcomes','eventId':d['id'],'eventAt':at,'data':d}


def captured(entries=None, launches=None, outcomes=None):
    launches=[launch()] if launches is None else launches
    return {'format':'launch-study-capture-1','sourceIdentity':'1:2','cutoffAt':T+400000,'windowStartAt':T-100000,
        'registration':{'version':'launch-registry-1','registeredAt':T-200000},'contextWindowStartAt':T-86500000,
        'earliestRetainedReceiptAt':min([l['availableAt'] for l in launches],default=None),
        'entries':[entry()] if entries is None else entries,'outcomes':[] if outcomes is None else outcomes,
        'matchedMintLaunchRecords':launches,'relatedLaunchContext':[
            {'mint':l['mint'],'availableAt':l['availableAt'],'traderReported':l['fields']['traderReported'],'metadataUriSha256':l['fields']['metadataUriSha256']} for l in launches],
        'readSeconds':0}


class StudyTests(unittest.TestCase):
    def test_strict_asof_excludes_current_mint_future_and_tied_receipts(self):
        c=captured();ls=[launch('E'*32,T-86400000),launch('F'*32,T-86400001),launch('G'*32,T),launch('H'*32,T+1)]
        c['relatedLaunchContext'] += captured(launches=ls)['relatedLaunchContext']
        r=analyze(c)['cases'][0]['launch']
        self.assertEqual(r['priorReceivedTraderLaunches24h'],1)
        self.assertEqual(r['priorReceivedSameUriHash24h'],1)
        self.assertIsNone(r['creatorReported'])
        self.assertEqual(r['reportedFields']['initialBuyReported'],'0')
        self.assertFalse(r['continuousFeedCoverageProven'])
        self.assertLess(r['lookbackCalendarSpanMs'],86400000)

    def test_no_future_launch_features_or_missing_identity_substitution(self):
        for ls,state in [([], 'no-retained-launch-record'),([launch(at=T+1)],'launch-received-after-signal')]:
            r=analyze(captured(launches=ls))['cases'][0]['launch']
            self.assertEqual(r['state'],state);self.assertIsNone(r['reportedFields']);self.assertEqual(r['traderGroup'],'unknown')
        c=captured(launches=[launch(trader=None,uri=None)]);c['matchedMintLaunchRecords'][0]['fields']['creatorReported']=TRADER
        r=analyze(c)['cases'][0]['launch'];self.assertIsNone(r['traderReported']);self.assertIsNone(r['priorReceivedTraderLaunches24h'])

    def test_zero_is_retained_window_zero_not_unknown_or_first_ever(self):
        r=analyze(captured())['cases'][0]['launch']
        self.assertEqual(r['priorReceivedTraderLaunches24h'],0)
        self.assertEqual(r['traderGroup'],'no-other-received-launches')

    def test_missing_self_context_cannot_silently_undercount_another_mint(self):
        c=captured();c['relatedLaunchContext']=captured(launches=[launch('E'*32)])['relatedLaunchContext']
        with self.assertRaisesRegex(ValueError,'current-mint'):analyze(c)

    def test_context_window_duplicate_and_future_caps_fail(self):
        for mutate in [lambda c:c.update(contextWindowStartAt=T),
                       lambda c:c['relatedLaunchContext'].append(c['relatedLaunchContext'][0]),
                       lambda c:c['relatedLaunchContext'][0].update(availableAt=T+500000)]:
            c=captured();mutate(c)
            with self.assertRaises(ValueError):analyze(c)

    def test_all_three_cohorts_recompute_returns_and_map_horizons(self):
        es=[entry(k,seq=i+1) for i,k in enumerate(('fast30-shadow','baseline','early-activity'))]
        os=[outcome(e,'60s' if i==0 else '1m',60000,100+i) for i,e in enumerate(es)]
        a=analyze(captured(entries=es,outcomes=os))
        self.assertEqual(len(a['cohorts']),3)
        for r in a['cases']:self.assertEqual(r['outcomes']['60s']['grossPriceChangePct'],50)

    def test_missing_gapped_pending_overdue_invalid_remain_in_denominator(self):
        es=[entry(at=T+i,seq=i+1) for i in range(5)]
        os=[outcome(es[0],status='missing'),outcome(es[1],coverage='gapped',seq=101),outcome(es[2],seq=102)]
        os[2]['data']['returnPct']=999
        c=captured(entries=es,outcomes=os);c['cutoffAt']=T+60003
        a=analyze(c);h=a['cohorts']['fast30-shadow']['horizons']['30s']
        self.assertEqual(h['states'],{'missing':1,'gapped':1,'invalid':1,'pending':2})
        self.assertEqual(h['grossPriceChange']['observed'],0)
        c['cutoffAt']+=1
        self.assertEqual(analyze(c)['cohorts']['fast30-shadow']['horizons']['30s']['states']['overdue'],1)

    def test_pool_and_clock_and_identity_mismatch_do_not_create_returns(self):
        for key,value in [('pairAddress','alternate'),('sampleAt',T+29999),('at',T+60001),('entryId','wrong')]:
            e=entry();o=outcome(e);o['data'][key]=value
            a=analyze(captured(outcomes=[o]));r=a['cases'][0]['outcomes']['30s']
            self.assertNotEqual(r['state'],'observed');self.assertIsNone(r['grossPriceChangePct'])

    def test_nonfinite_prices_and_unsupported_versions_visible_as_exclusions(self):
        for key,value in [('priceUsd',float('nan')),('version','unknown')]:
            e=entry();e['data'][key]=value;a=analyze(captured(entries=[e]))
            self.assertEqual(a['sourceEntries'],1);self.assertEqual(a['analyzedEntries'],0);self.assertEqual(len(a['excludedEntries']),1)

    def test_duplicate_entries_and_horizons_fail_instead_of_double_count(self):
        c=captured();c['entries']*=2
        with self.assertRaises(ValueError):analyze(c)
        c=captured(outcomes=[outcome(entry()),outcome(entry(),seq=101)])
        with self.assertRaises(ValueError):analyze(c)

    def test_groups_preserve_liquidity_unknown_and_followup_selection(self):
        e=entry();e['data']['liquidityUsd']=None;e['data']['followup']['admitted']=False
        a=analyze(captured(entries=[e]));g=a['contrasts'][0]
        self.assertEqual(g['liquidityGroup'],'unknown');self.assertEqual(g['followupAdmitted'],'False')
        self.assertEqual(a['hourBlocks'][0]['entries'],1)

    def test_tail_summary_does_not_hide_outlier_and_singleton(self):
        d=distribution([-99,-50,0,1000]);self.assertEqual(d['lossAtLeast50'],2)
        self.assertAlmostEqual(d['meanWithoutBestPct'],-149/3)
        self.assertIsNone(distribution([1])['meanWithoutBestPct']);self.assertIsNone(distribution([])['meanPct'])

    def database(self,path,es=None):
        c=captured(entries=es)
        with sqlite3.connect(path) as db:
            db.executescript('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,id TEXT,at INTEGER,data TEXT,UNIQUE(kind,id));CREATE INDEX events_at ON events(kind,at);CREATE TABLE kv(key TEXT PRIMARY KEY,data TEXT);CREATE TABLE launch_registry(mint TEXT PRIMARY KEY,received_at INTEGER,data TEXT);CREATE INDEX launch_registry_received ON launch_registry(received_at);')
            db.execute('INSERT INTO kv VALUES(?,?)',('launch-registry-registration',json.dumps(c['registration'])))
            db.execute('INSERT INTO kv VALUES(?,?)',('health',json.dumps({'lastLoopAt':T,'lastMarketAt':T-1})))
            for l in c['matchedMintLaunchRecords']:db.execute('INSERT INTO launch_registry VALUES(?,?,?)',(l['mint'],l['receivedAt'],json.dumps(l)))
            for i,e in enumerate(c['entries']):
                for row in [e,outcome(e,seq=100+i)]:
                    data=copy.deepcopy(row['data'])
                    if 'entryPool' in data:data['evidence']={'entryPool':data.pop('entryPool')}
                    db.execute('INSERT INTO events VALUES(?,?,?,?,?)',(row['seq'],row['kind'],row['eventId'],row['eventAt'],json.dumps(data)))
        return path

    def test_real_sqlite_capture_projection_no_snapshot_or_current_candidate_dependency(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.database(Path(d)/'db',[entry('baseline'),entry(seq=2)])
            before=hashlib.sha256(f.read_bytes()).hexdigest();c=capture(f,now=T+400000)
            a=analyze(c);self.assertEqual(a['analyzedEntries'],2)
            for r in a['cases']:self.assertEqual(r['outcomes']['30s']['grossPriceChangePct'],50)
            self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),before)
            self.assertIsNone(c['healthSnapshot']['snapshotAt']);self.assertEqual(c['healthSnapshot']['lastLoopAt'],T)

    def test_collector_caps_deadline_and_oversized_rows_fail(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.database(Path(d)/'db')
            with self.assertRaisesRegex(ValueError,'Entry cap'):capture(f,now=T+400000,max_entries=0)
            with self.assertRaises((TimeoutError,sqlite3.OperationalError)):capture(f,now=T+400000,budget=-0.5)
            with sqlite3.connect(f) as db:db.execute("UPDATE events SET data=? WHERE kind='fast-shadow-entries'",('x'*262145,))
            with self.assertRaisesRegex(ValueError,'cap'):capture(f,now=T+400000)

    def test_future_outcomes_and_entries_before_registration_are_not_captured(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.database(Path(d)/'db',[entry(),entry(at=T-300000,seq=2)])
            c=capture(f,now=T+10000)
            self.assertEqual(len(c['entries']),1);self.assertEqual(c['outcomes'],[])

    def test_replay_same_analysis_atomic_private_publication_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            c=captured(outcomes=[outcome(entry())]);f=Path(d)/'report.json.gz'
            report={'format':'launch-study-report-1','capture':c,'analysis':analyze(c)}
            publish(f,report);self.assertEqual(f.stat().st_mode&0o777,0o600)
            self.assertEqual(analyze(read_capture(f)),report['analysis'])
            before=f.read_bytes()
            with self.assertRaises(FileExistsError):publish(f,report)
            self.assertEqual(f.read_bytes(),before);self.assertEqual(len(list(Path(d).iterdir())),1)

    def test_cli_replay_and_failure_publish_no_partial(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'input.gz';out=root/'out.gz';c=captured()
            publish(source,{'format':'launch-study-report-1','capture':c})
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('report.py')),'--input',str(source),'--output',str(out)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(analyze(read_capture(out)),analyze(c))
            bad=root/'bad.gz';bad.write_bytes(b'invalid');missing=root/'missing.gz'
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('report.py')),'--input',str(bad),'--output',str(missing)],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertFalse(missing.exists())

    def test_actual_scanner_research_producer_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(__file__).resolve().parents[1]
            script="""
import {Storage} from './scanner/src/core/storage.js';
import {Research} from './scanner/src/core/research.js';
import {creationEvidence} from './scanner/src/core/launch-registry.js';
const at=Date.now(),mint='A'.repeat(32),pool='B'.repeat(32);
const storage=new Storage(process.argv[1]);
const registry=storage.launchRegistry;
registry.record(creationEvidence({txType:'create',mint,traderPublicKey:'C'.repeat(32),initialBuy:0},at-1000),at-1000);
const research=new Research({researchEnabled:true,securityTtlMs:300000},storage);
const c={mint,pairAddress:pool,priceUsd:2,marketObservedAt:at,liquidityUsd:10000};
research.baseline(c,at);
research.startEntry(c,research.state(mint),'early-activity',at,null);
research.checkpoint(mint,research.state(mint),{...c,marketObservedAt:at+30000,priceUsd:3},at+30000,true);
storage.close();console.log(at);
"""
            r=subprocess.run(['node','--input-type=module','-e',script,d],cwd=root,text=True,capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr);at=int(r.stdout.strip())
            a=analyze(capture(Path(d)/'radar.sqlite',now=at+40000))
            self.assertEqual(a['analyzedEntries'],2)
            for row in a['cases']:
                self.assertEqual(row['outcomes']['30s']['grossPriceChangePct'],50)
                self.assertEqual(row['launch']['priorReceivedTraderLaunches24h'],0)
                self.assertIsNone(row['launch']['creatorReported'])

    def test_report_and_decompressed_input_size_caps(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'report.gz'
            with patch('report.MAX_REPORT_BYTES',2):
                with self.assertRaises(ValueError):publish(f,{'too':'large'})
            self.assertFalse(f.exists());f.write_bytes(gzip.compress(b'x'*100))
            with patch('report.MAX_REPORT_BYTES',10):
                with self.assertRaises(ValueError):read_capture(f)

if __name__=='__main__':unittest.main()
