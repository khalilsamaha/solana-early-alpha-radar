import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import accounting_inspect as a
from test_event_inspect import LAYOUT, accepted, defaults, encode, key
from test_schema_compare import candidate_tx


def roles(tx):
    spec = next(d for d in LAYOUT["instructions"] if d["name"] == "buy_v2")
    return dict(zip([v["name"] for v in spec["accounts"]], tx["transaction"]["message"]["instructions"][1]["accounts"]))


def change_trade(tx, **changes):
    event = tx["meta"]["innerInstructions"][1]["instructions"][-1]
    layout, _ = a.schema.candidate_layout()
    definition = next(x for x in layout["events"] if x["name"] == "TradeEvent")
    values = a.base.decode_event(a.base.b58decode(event["data"])[8:], definition, layout)
    values.update(changes)
    event["data"] = a.base.b58encode(a.base.EVENT_TAG + a.schema.encode_event(values, definition, layout))


def fixture():
    tx = candidate_tx()
    r = roles(tx)
    create = defaults("CreateEvent")
    create.update(mint=r["base_mint"], bonding_curve=r["bonding_curve"], user=r["user"], creator=r["user"],
                  token_program=r["base_token_program"], quote_mint=a.base.SYSTEM,
                  virtual_token_reserves=2000, real_token_reserves=1000, token_total_supply=1000,
                  virtual_sol_reserves=10000, virtual_quote_reserves=10000)
    tx["meta"]["innerInstructions"][0]["instructions"][-1]["data"] = a.base.b58encode(a.base.EVENT_TAG+encode("CreateEvent", create))
    change_trade(tx, creator=r["user"], fee_recipient=r["fee_recipient"], fee=5, fee_basis_points=95,
                 creator_fee=2, creator_fee_basis_points=30, buyback_fee=2, buyback_fee_basis_points=5000,
                 virtual_token_reserves=1877, real_token_reserves=877, virtual_sol_reserves=10456,
                 real_sol_reserves=456, virtual_quote_reserves=10456, real_quote_reserves=456)
    parent = tx["transaction"]["message"]["instructions"][1]
    parent["data"] = a.base.b58encode(a.base.b58decode(parent["data"])[:8]+(123).to_bytes(8,"little")+(463).to_bytes(8,"little"))
    ins = tx["meta"]["innerInstructions"][1]["instructions"]
    extra = []
    for target, amount, kind in (("creator_vault",7,"transfer"),("creator_vault",2,"transfer"),
                                  ("fee_recipient",3,"transfer"),("buyback_fee_recipient",2,"transfer"),
                                  ("user_volume_accumulator",11,"createAccount")):
        extra.append({"programId":a.base.SYSTEM,"stackHeight":2,"parsed":{"type":kind,"info":{
            "source":r["user"],"destination" if kind=="transfer" else "newAccount":r[target],"lamports":amount}}})
    ins[-1:-1] = extra
    entries = tx["transaction"]["message"]["accountKeys"]
    entries.sort(key=lambda x:x["pubkey"] != r["user"])
    keys = [x["pubkey"] for x in entries]
    before = [1000000 if k==r["user"] else 0 for k in keys]
    after = before.copy()
    after[0] -= 484  # 456 curve + 5 protocol + 2 creator + 7 extra + 11 creation + 3 network.
    for name, amount in (("bonding_curve",456),("creator_vault",9),("fee_recipient",3),("buyback_fee_recipient",2),("user_volume_accumulator",11)):
        after[keys.index(r[name])] += amount
    tx["meta"].update(preBalances=before, postBalances=after, fee=3)
    return tx


class AccountingTests(unittest.TestCase):
    def inspect(self, tx):
        report,bundle,_=accepted(tx)
        return a.inspect(report,bundle)

    def test_split_fees_extra_transfer_and_full_wallet_debit_stay_distinct(self):
        result=self.inspect(fixture()); case=result["cases"][0]
        self.assertEqual(case["state"],"observed-accounting-consistent-live-blocked")
        self.assertTrue(all(case["checks"].values()))
        self.assertEqual(case["trade"]["trade_plus_reported_fees_lamports"],463)
        self.assertEqual(case["trade"]["additional_creator_vault_lamports"],7)
        self.assertEqual(case["trade"]["additional_buy_parent_outflows_lamports"],18)
        self.assertEqual(case["trade"]["buy_parent_create_account_lamports"],11)
        self.assertEqual(case["cashflows"]["user_observed_net_debit_lamports"],484)
        self.assertEqual(case["cashflows"]["absolute_residual_lamports"],0)
        for flag in ("fee_model_verified","historical_fee_config_verified","historical_curve_accounts_verified",
                     "deployed_program_version_verified","curve_reconstruction_accepted","profitability_evaluated"):
            self.assertIs(result[flag],False)
        self.assertFalse(case["additional_transfer_purpose_verified"])

    def test_reserve_recipient_mode_and_fee_arithmetic_mismatches_do_not_pass(self):
        for changes in ({"virtual_token_reserves":1876},{"real_token_reserves":876},{"virtual_sol_reserves":10457},
                        {"real_sol_reserves":455},{"virtual_quote_reserves":10457},{"creator":key(999)},
                        {"fee_recipient":key(999)},{"mayhem_mode":True},{"fee_basis_points":120},
                        {"creator_fee_basis_points":1},{"buyback_fee_basis_points":0}):
            with self.subTest(changes=changes):
                tx=fixture();change_trade(tx,**changes)
                case=self.inspect(tx)["cases"][0]
                self.assertEqual(case["state"],"accounting-mismatch")

    def test_duplicate_creator_fee_cannot_be_assigned_arbitrarily(self):
        tx=fixture();ins=tx["meta"]["innerInstructions"][1]["instructions"]
        ins[-1:-1]=[copy.deepcopy(ins[3])]
        case=self.inspect(tx)["cases"][0]
        self.assertEqual(case["state"],"accounting-mismatch")
        self.assertFalse(case["checks"]["creator_fee_has_unique_matching_transfer"])
        self.assertIsNone(case["trade"]["additional_creator_vault_lamports"])

    def test_cap_excludes_extra_account_funding_but_includes_reported_fees(self):
        tx=fixture();parent=tx["transaction"]["message"]["instructions"][1]
        parent["data"]=a.base.b58encode(a.base.b58decode(parent["data"])[:16]+(462).to_bytes(8,"little"))
        case=self.inspect(tx)["cases"][0]
        self.assertFalse(case["checks"]["trade_and_reported_fees_within_instruction_cap"])
        self.assertEqual(case["state"],"accounting-mismatch")

    def test_unknown_fee_modes_and_argument_tails_are_unsupported(self):
        for changes in ({"quote_transfer_fee":1},{"holder_rewards":1},{"cashback":1},{"creator_fee_unclaimed":1},
                        {"shareholders":[{"address":key(99),"share_bps":10000}]},{"fee_basis_points":10001}):
            tx=fixture();change_trade(tx,**changes)
            self.assertEqual(self.inspect(tx)["cases"][0]["state"],"unsupported-or-inconsistent-accounting-evidence")
        tx=fixture();parent=tx["transaction"]["message"]["instructions"][1]
        parent["data"]=a.base.b58encode(a.base.b58decode(parent["data"])+b"\0")
        self.assertEqual(self.inspect(tx)["cases"][0]["state"],"unsupported-or-inconsistent-accounting-evidence")

    def test_all_accounts_checked_not_just_user_or_global_sum(self):
        tx=fixture();r=roles(tx);keys=[x['pubkey'] for x in tx['transaction']['message']['accountKeys']]
        tx["meta"]["postBalances"][keys.index(r['bonding_curve'])]+=1
        tx["meta"]["postBalances"][keys.index(r['creator_vault'])]-=1
        case=self.inspect(tx)["cases"][0]
        self.assertEqual(case["state"],"accounting-mismatch")
        self.assertEqual(case["cashflows"]["unmatched_account_count"],2)
        self.assertEqual(case["cashflows"]["absolute_residual_lamports"],2)

    def test_event_order_stack_and_aliased_fee_roles_remain_unsupported(self):
        for kind in ('event-order','stack','alias'):
            tx=fixture();ins=tx['meta']['innerInstructions'][1]['instructions']
            if kind=='event-order':ins[-1],ins[-2]=ins[-2],ins[-1]
            elif kind=='stack':ins[2]['stackHeight']=3
            else:
                parent=tx['transaction']['message']['instructions'][1]
                parent['accounts'][8]=parent['accounts'][6]
            self.assertEqual(self.inspect(tx)['cases'][0]['state'],'unsupported-or-inconsistent-accounting-evidence')

    def test_wrong_fee_or_missing_balances_cannot_pass(self):
        tx=fixture();tx["meta"]["fee"]=4
        self.assertEqual(self.inspect(tx)["cases"][0]["state"],"accounting-mismatch")
        tx=fixture();del tx["meta"]["preBalances"]
        self.assertEqual(self.inspect(tx)["cases"][0]["state"],"unsupported-or-inconsistent-accounting-evidence")

    def test_cashflows_reject_ambiguous_keys_groups_and_noninteger_amounts(self):
        for kind in ("keys","groups","bool","float","negative","overflow","unparsed-system","unknown-system"):
            tx=fixture();r=roles(tx)
            if kind=="keys":tx["transaction"]["message"]["accountKeys"][1]=tx["transaction"]["message"]["accountKeys"][0]
            elif kind=="groups":tx["meta"]["innerInstructions"].append(tx["meta"]["innerInstructions"][0])
            elif kind=="unparsed-system":del tx["meta"]["innerInstructions"][1]["instructions"][1]["parsed"]
            elif kind=="unknown-system":tx["meta"]["innerInstructions"][1]["instructions"][1]["parsed"]["type"]="transferWithSeed"
            else:tx["meta"]["fee"]={"bool":True,"float":3.0,"negative":-1,"overflow":2**64}[kind]
            with self.assertRaises(a.CaptureError):a.cashflows(tx,r["user"])

    def test_separate_fee_payer_and_incoming_transfer_accounted(self):
        tx=fixture();r=roles(tx);entries=tx["transaction"]["message"]["accountKeys"]
        entries[0],entries[1]=entries[1],entries[0];entries[0]["signer"]=True
        for field in ("preBalances","postBalances"):
            b=tx["meta"][field];b[0],b[1]=b[1],b[0]
        tx["meta"]["preBalances"][0]+=100
        tx["meta"]["postBalances"][0]+=92
        tx["meta"]["postBalances"][1]+=8
        tx["transaction"]["message"]["instructions"].append({"programId":a.base.SYSTEM,"parsed":{"type":"transfer","info":{
            "source":entries[0]["pubkey"],"destination":r["user"],"lamports":5}}})
        ledger,_=a.cashflows(tx,r["user"])
        self.assertTrue(ledger["all_account_net_deltas_match"])
        self.assertFalse(ledger["user_pays_transaction_fee"])
        self.assertEqual(ledger["user_system_inflows_lamports"],5)
        self.assertEqual(ledger["user_explained_net_debit_lamports"],476)

    def test_create_only_is_not_a_trade_or_lifetime_claim(self):
        tx=fixture();tx["transaction"]["message"]["instructions"].pop();tx["meta"]["innerInstructions"].pop()
        tx["meta"]["postBalances"]=tx["meta"]["preBalances"].copy();tx["meta"]["postBalances"][0]-=3
        case=self.inspect(tx)["cases"][0]
        self.assertEqual(case["state"],"creation-only-accounting-consistent")
        self.assertFalse(case["trade_observed"])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        report,_,compressed=accepted(fixture())
        self.report=self.root/'report.json';self.report.write_text(json.dumps(report))
        self.bundle=self.root/'evidence.json.gz';self.bundle.write_bytes(compressed)
        self.output=self.root/'output.json'
    def tearDown(self):self.temp.cleanup()
    def call(self,extra=()):
        self.messages=io.StringIO()
        with patch('socket.socket',side_effect=AssertionError('network forbidden')),contextlib.redirect_stdout(self.messages),contextlib.redirect_stderr(self.messages):
            return a.main(['--rpc-report',str(self.report),'--evidence',str(self.bundle),'--output',str(self.output),*extra])
    def test_offline_private_preserving_and_no_identity_export(self):
        before=[p.read_bytes() for p in (self.report,self.bundle)]
        self.assertEqual(self.call(),0)
        result=json.loads(self.output.read_text())
        self.assertEqual(result['cases'][0]['state'],'observed-accounting-consistent-live-blocked')
        self.assertFalse(result['network_used']);self.assertEqual(result['transactions_sent'],0)
        self.assertEqual(before,[p.read_bytes() for p in (self.report,self.bundle)])
        self.assertEqual(self.output.stat().st_mode&0o777,0o600)
        for address in roles(fixture()).values():self.assertNotIn(address,self.output.read_text())
    def test_corruption_limits_and_existing_output_fail_safely(self):
        with patch.object(a.base,'MAX_INPUT',32):self.assertEqual(self.call(),1)
        self.assertFalse(self.output.exists())
        self.bundle.write_bytes(self.bundle.read_bytes()+b'x');self.assertEqual(self.call(),1)
        self.assertFalse(self.output.exists())
        self.output.write_text('preserve');self.assertEqual(self.call(),1)
        self.assertEqual(self.output.read_text(),'preserve')
    def test_source_replay_and_schema_pins_are_required(self):
        report=json.loads(self.report.read_text());report['source_sha256']['rpc_probe.py']='bad'
        self.report.write_text(json.dumps(report));self.assertEqual(self.call(),1)
        self.assertFalse(self.output.exists())
    def test_invalid_arguments_are_sanitized(self):
        self.assertEqual(self.call(('--key','SENSITIVE-KEY')),1)
        self.assertNotIn('SENSITIVE-KEY',self.messages.getvalue())
        self.assertFalse(self.output.exists())
