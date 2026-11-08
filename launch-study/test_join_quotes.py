import copy
import gzip
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from join_quotes import join, USDC, OFFSETS
from joined_report import build, read
from report import publish
from test_study import captured, entry, outcome, T, M, P


def fixture(cohort='fast30-shadow', level=1):
    e=entry(cohort);c=captured(entries=[e],outcomes=[outcome(e)])
    event_id=e['eventId'] if cohort!='baseline' else f'{M}:{T}:{level}'
    s={'seq':e['seq'] if cohort!='baseline' else 900,'cohort':cohort,'entryId':event_id,'eventId':event_id,
       'mint':M,'signalAt':T,'originalPool':P,'entryPriceUsd':2,'detectedAt':T+500,
       'samplingPolicy':'three-cohort-budgets-v3','decision':'admitted'}
    buy={'leg':'buy','status':'quoted','startedAt':T+700,'receivedAt':T+1000,'inputMint':USDC,'outputMint':M,
         'inAmount':'10000000','outAmount':'1000000000000000000','transactionRequested':False,'executionVerified':False,
         'routePlan':[{'pool':P,'inputMint':USDC,'outputMint':M}],'routePlanTruncated':False}
    sells=[{'leg':'sell','targetOffsetMs':h,'status':'quoted','startedAt':T+1000+max(h,10000),'receivedAt':T+1300+max(h,10000),
         'inputMint':M,'outputMint':USDC,'inAmount':buy['outAmount'],'outAmount':'11000000','quotedUsdcChangePct':10,
         'transactionRequested':False,'executionVerified':False,
         'routePlan':[{'pool':P,'inputMint':M,'outputMint':USDC}],'routePlanTruncated':False} for h in OFFSETS]
    p={'signal':copy.deepcopy(s),'state':'complete','samplingPolicy':s['samplingPolicy'],'mint':M,'baseMint':USDC,
       'inputAtomic':'10000000','observations':[buy,*sells],'finishedAt':T+122000}
    q={'format':'quote-observer-report-0.2.0','sourceIdentity':c['sourceIdentity'],'capturedAt':c['cutoffAt'],
       'windowStartAt':c['windowStartAt'],'signals':[s],'probes':[p]}
    return c,q


class JoinTests(unittest.TestCase):
    def test_three_cohorts_and_level_two_first_baseline_alert(self):
        for cohort in ('baseline','early-activity','fast30-shadow'):
            c,q=fixture(cohort,2);a=join(c,q);r=a['cases'][0]
            self.assertEqual(a['matchedObserverDecisions'],1);self.assertEqual(a['admitted'],1)
            self.assertEqual(r['quote']['exits']['30000']['quotedChangePct'],10)
            self.assertEqual(r['quote']['exits']['30000']['paperChangePct'],50)
            self.assertEqual(r['quote']['exits']['30000']['paperMinusQuoteReceiptMs'],-1300)
            if cohort=='baseline':self.assertNotEqual(r['sourceSeq'],r['observer']['seq'])

    def test_source_mismatch_and_duplicate_sequences_fail(self):
        c,q=fixture();q['sourceIdentity']='other'
        with self.assertRaisesRegex(ValueError,'Source identity'):join(c,q)
        for key in ('signals','probes'):
            c,q=fixture();q[key]*=2
            with self.assertRaisesRegex(ValueError,'Duplicate'):join(c,q)

    def test_mint_pool_price_time_and_sequence_mismatch_never_create_joined_returns(self):
        for field,value in [('mint','D'*32),('originalPool','D'*32),('entryPriceUsd',3),('signalAt',T+1),('seq',999)]:
            c,q=fixture();q['signals'][0][field]=value
            a=join(c,q)
            self.assertEqual(a['admitted'],0)
            self.assertIsNone(a['cases'][0]['quote']['exits']['30000']['quotedChangePct'])

    def test_probe_identity_mismatch_cannot_replace_exported_admission(self):
        c,q=fixture();q['probes'][0]['signal']['originalPool']='D'*32
        r=join(c,q)['cases'][0]
        self.assertEqual(r['quote']['buy']['state'],'probe-identity-mismatch')
        self.assertIsNone(r['quote']['exits']['30000']['quotedChangePct'])

    def test_unadmitted_unknown_and_missing_probe_keep_denominators(self):
        c,q=fixture();q['signals'][0]['decision']='observer-busy';q['probes']=[]
        a=join(c,q);self.assertEqual(a['groups'][0]['entries'],1);self.assertEqual(a['admitted'],0)
        self.assertEqual(a['groups'][0]['horizons']['30000']['states'],{'not-admitted':1})
        q['signals']=[];a=join(c,q)
        self.assertEqual(a['cases'][0]['observer']['state'],'no-observer-signal-in-export')
        c,q=fixture();q['probes']=[]
        self.assertEqual(join(c,q)['cases'][0]['quote']['buy']['state'],'admitted-probe-not-exported')

    def test_wrong_quantities_tokens_or_stored_return_never_count_as_valid(self):
        for key,value in [('inAmount','999999999999999999'),('inputMint',USDC),('outAmount','0'),('quotedUsdcChangePct',99),('executionVerified',True)]:
            c,q=fixture();q['probes'][0]['observations'][2][key]=value
            r=join(c,q)['cases'][0]['quote']['exits']['30000']
            self.assertEqual(r['state'],'invalid-exit-quantity-mint-or-return');self.assertIsNone(r['quotedChangePct'])

    def test_changed_notional_and_invalid_buy_do_not_mix_experiments(self):
        c,q=fixture();p=q['probes'][0];p['inputAtomic']='20000000';p['observations'][0]['inAmount']='20000000'
        a=join(c,q);self.assertEqual(a['groups'][0]['horizons']['30000']['quotedChange']['observed'],0)
        self.assertEqual(a['cases'][0]['quote']['buy']['state'],'invalid-buy-evidence')

    def test_buy_and_sell_failures_not_assigned_zero_or_loss(self):
        c,q=fixture();q['probes'][0]['observations'][2]['status']='http-error'
        a=join(c,q);self.assertEqual(a['cases'][0]['quote']['exits']['30000']['state'],'sell-quote-failed')
        self.assertEqual(a['groups'][0]['horizons']['30000']['quotedChange']['observed'],0)
        q['probes'][0]['observations'][0]['status']='no-route-evidence'
        a=join(c,q);self.assertEqual(a['cases'][0]['quote']['buy']['state'],'buy-quote-failed')
        self.assertEqual(a['groups'][0]['horizons']['120000']['quotedChange']['observed'],0)

    def test_common_cutoff_recomputes_paper_and_excludes_future_quotes(self):
        c,q=fixture();q['capturedAt']=T+20000
        a=join(c,q);x=a['cases'][0]['quote']['exits']['30000']
        self.assertEqual(x['paperState'],'pending');self.assertIsNone(x['paperChangePct'])
        self.assertEqual(x['state'],'after-cutoff');self.assertIsNone(x['quotedChangePct'])
        self.assertEqual(a['wholeQuoteExportGroups'][0]['horizons']['30000']['quotedChange']['observed'],0)

    def test_future_observer_detection_is_not_past_admission(self):
        c,q=fixture();c['cutoffAt']=T+100
        a=join(c,q);self.assertEqual(a['admitted'],0)
        self.assertEqual(a['cases'][0]['observer']['state'],'observer-detected-after-cutoff')

    def test_whole_export_stays_separate_when_entry_outside_common_window(self):
        c,q=fixture();q['windowStartAt']=T+1
        a=join(c,q);self.assertEqual(a['commonWindowEntries'],0);self.assertEqual(len(a['studyEntriesOutsideCommonWindow']),1)
        self.assertEqual(a['wholeQuoteExportGroups'][0]['admitted'],1)
        self.assertEqual(a['wholeQuoteExportGroups'][0]['horizons']['120000']['quotedChange']['meanPct'],10)
        q['windowStartAt']=q['capturedAt']+1
        with self.assertRaises(ValueError):join(c,q)

    def test_routes_are_recomputed_and_truncated_routes_remain_unknown(self):
        c,q=fixture();sell=q['probes'][0]['observations'][2]
        sell['originalPoolInRoute']=True;sell['routePlan'][0]['pool']='D'*32
        x=join(c,q)['cases'][0]['quote']['exits']['30000']
        self.assertFalse(x['route']['originalPoolPresent']);self.assertTrue(x['tokenRouteChanged'])
        sell['routePlanTruncated']=True
        x=join(c,q)['cases'][0]['quote']['exits']['30000'];self.assertIsNone(x['route']['originalPoolPresent'])
        self.assertEqual(x['quotedChangePct'],10)  # Amount evidence remains, route provenance is unknown.

    def test_late_quotes_remain_visible_but_not_in_on_time_summary(self):
        c,q=fixture();sell=q['probes'][0]['observations'][2]
        sell.update(startedAt=T+37000,receivedAt=T+37300)
        a=join(c,q);h=a['groups'][0]['horizons']['30000']
        self.assertEqual(h['quotedChange']['observed'],1);self.assertEqual(h['onTimeQuotedChange']['observed'],0)
        self.assertEqual(h['lateBeyond5s'],1)
        sell.update(startedAt=T+31000,receivedAt=T+40000)
        h=join(c,q)['groups'][0]['horizons']['30000'];self.assertEqual(h['onTimeQuotedChange']['observed'],0)

    def test_untimed_skips_need_completion_evidence_at_cutoff(self):
        c,q=fixture();q['probes'][0]['observations'][2]={'leg':'sell','targetOffsetMs':30000,'status':'skipped','reason':'rate-limited'}
        self.assertEqual(join(c,q)['cases'][0]['quote']['exits']['30000']['state'],'not-sampled')
        q['probes'][0]['finishedAt']=c['cutoffAt']+1
        self.assertEqual(join(c,q)['cases'][0]['quote']['exits']['30000']['state'],'skip-time-unavailable')

    def test_missing_exit_pending_or_overdue_and_duplicate_offsets_rejected(self):
        c,q=fixture();q['probes'][0]['observations']=q['probes'][0]['observations'][:1];q['probes'][0]['state']='running';q['probes'][0].pop('finishedAt')
        self.assertEqual(join(c,q)['cases'][0]['quote']['exits']['30000']['state'],'overdue-unrecorded')
        c['cutoffAt']=T+20000
        self.assertEqual(join(c,q)['cases'][0]['quote']['exits']['30000']['state'],'unfinished-at-cutoff')
        c,q=fixture();q['probes'][0]['observations'][3]['targetOffsetMs']=30000
        with self.assertRaisesRegex(ValueError,'Duplicate/unsupported'):join(c,q)

    def test_launch_contrasts_include_skips_unknowns_and_sampling_policy(self):
        c,q=fixture();q['signals'][0]['decision']='hour-budget';q['probes']=[]
        a=join(c,q);g=a['launchContrasts'][0]
        self.assertEqual(g['entries'],1);self.assertEqual(g['admitted'],0)
        self.assertEqual(g['samplingPolicy'],'three-cohort-budgets-v3')
        self.assertEqual(g['horizons']['30000']['states'],{'not-admitted':1})

    def test_buy_before_observer_detection_is_invalid(self):
        c,q=fixture();q['probes'][0]['observations'][0]['startedAt']=T+100
        a=join(c,q)
        self.assertEqual(a['cases'][0]['quote']['buy']['state'],'invalid-buy-evidence')
        self.assertEqual(a['groups'][0]['horizons']['30000']['quotedChange']['observed'],0)

    def run_wrapper(self,fail=False):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);project=root/'project';project.mkdir()
            (project/'src').mkdir();(project/'scripts').mkdir()
            c,q=fixture();sf=root/'study.gz';qf=root/'quotes.gz'
            publish(sf,{'format':'launch-study-report-1','capture':c});publish(qf,q)
            stub=root/'sudo'
            stub.write_text("#!/usr/bin/env python3\n" + """import os,sys,shutil
from pathlib import Path
args=sys.argv[1:]
assert args[:3]==['python3','-E','-s']
if args[3].endswith('/report.py'):
    assert args[4:]==['--project',os.getcwd(),'--hours','6','--output',args[-1]]
    shutil.copyfile(os.environ['TEST_STUDY'],args[-1])
elif args[3:]==['/usr/local/lib/solana-radar-quotes/0.9.0/manage.py','export','--hours','7']:
    if os.environ.get('TEST_EXPORT_FAIL')=='1':sys.exit(8)
    sys.stdout.buffer.write(Path(os.environ['TEST_QUOTES']).read_bytes())
else:sys.exit(9)
""")
            stub.chmod(0o700)
            env={**os.environ,'PATH':str(root)+os.pathsep+os.environ['PATH'],'TEST_STUDY':str(sf),'TEST_QUOTES':str(qf),'TEST_EXPORT_FAIL':str(int(fail))}
            cmd=['bash',str(Path(__file__).with_name('run-joined.sh').resolve()),'--hours','6']
            r=subprocess.run(cmd,cwd=project,env=env,capture_output=True,text=True)
            self.assertFalse(list(project.glob('.launch-join-*')))
            outputs=list(project.glob('radar-launch-quotes-*.json.gz'))
            if fail:
                self.assertNotEqual(r.returncode,0);self.assertEqual(outputs,[])
            else:
                self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(len(outputs),1)
                self.assertEqual(read(outputs[0])[0]['analysis']['admitted'],1)
                self.assertEqual(outputs[0].stat().st_mode&0o777,0o600)

    def test_wrapper_joins_sequential_reads_with_padded_quote_window(self):
        self.run_wrapper()

    def test_wrapper_failed_export_cleans_temporary_files_without_publication(self):
        self.run_wrapper(fail=True)

    def test_cli_replay_recomputes_analysis_and_preserves_private_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c,q=fixture();study={'format':'launch-study-report-1','capture':c,'analysis':{'fake':'ignored'}}
            sf=root/'study.gz';qf=root/'quotes.gz';out=root/'joined.gz';replay=root/'replay.gz'
            publish(sf,study);publish(qf,q)
            cmd=[sys.executable,str(Path(__file__).with_name('joined_report.py'))]
            r=subprocess.run([*cmd,'--study',str(sf),'--quotes',str(qf),'--output',str(out)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(out.stat().st_mode&0o777,0o600)
            original=read(out)[0];original['analysis']={'tampered':'derived summary'}
            old=root/'old.gz';publish(old,original)
            r=subprocess.run([*cmd,'--input',str(old),'--output',str(replay)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(read(out)[0],read(replay)[0])
            q['sourceIdentity']='different';bad=root/'bad.gz';publish(bad,q);missing=root/'missing.gz'
            r=subprocess.run([*cmd,'--study',str(sf),'--quotes',str(bad),'--output',str(missing)],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertFalse(missing.exists())

if __name__=='__main__':unittest.main()
