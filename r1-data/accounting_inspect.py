"""Offline native-SOL transaction accounting; no historical fee-model acceptance."""
import gzip
import io
import os
from pathlib import Path
import sys
import tempfile

import schema_compare as schema
from capture import CaptureError, canonical, exclusive_file, strict_json, sync_dir
from rpc_probe import Parser

base = schema.base
ROOT = Path(__file__).resolve().parent
SOURCES = ("accounting_inspect.py", *schema.SOURCES)


def uint(value):
    if type(value) is not int or not 0 <= value < 2**64:
        raise CaptureError("integer-range")
    return value


def cashflows(tx, user):
    """Count each parsed System move once and compare every account's net delta.

    Other programs can change lamports directly. Any unexplained net delta stays
    a mismatch; agreement is evidence consistency, not execution authentication.
    """
    message, meta = tx["transaction"]["message"], tx["meta"]
    entries = message["accountKeys"]
    keys = [x["pubkey"] for x in entries]
    if len(keys) != len(set(keys)) or not keys or entries[0]["signer"] is not True:
        raise CaptureError("account-keys")
    before, after = meta["preBalances"], meta["postBalances"]
    if len(before) != len(keys) or len(after) != len(keys):
        raise CaptureError("balance-length")
    actual = [uint(q)-uint(p) for p, q in zip(before, after)]
    positions = {key: i for i, key in enumerate(keys)}
    expected = [0] * len(keys)
    fee = uint(meta["fee"])
    expected[0] -= fee
    instructions = [(i, ins) for i, ins in enumerate(message["instructions"])]
    seen = set()
    for group in meta["innerInstructions"]:
        index = group["index"]
        if type(index) is not int or index in seen or not 0 <= index < len(message["instructions"]):
            raise CaptureError("inner-group")
        seen.add(index)
        instructions.extend((index, ins) for ins in group["instructions"])
    moves = []
    for parent, ins in instructions:
        if ins.get("programId") != base.SYSTEM:
            continue
        parsed = ins.get("parsed", {})
        kind, info = parsed.get("type"), parsed.get("info", {})
        if kind not in ("transfer", "createAccount"):
            raise CaptureError("unsupported-system-move")
        source = info["source"]
        destination = info["destination" if kind == "transfer" else "newAccount"]
        amount = uint(info["lamports"])
        if source == destination:
            raise CaptureError("aliased-move")
        expected[positions[source]] -= amount
        expected[positions[destination]] += amount
        moves.append({"parent": parent, "kind": kind, "source": source,
                      "destination": destination, "lamports": amount, "stack_height": ins.get("stackHeight")})
    incoming = sum(x["lamports"] for x in moves if x["destination"] == user)
    outgoing = sum(x["lamports"] for x in moves if x["source"] == user)
    user_fee = fee if keys[0] == user else 0
    residuals = [a-e for a, e in zip(actual, expected)]
    return {"all_account_net_deltas_match": not any(residuals),
            "unmatched_account_count": sum(x != 0 for x in residuals),
            "absolute_residual_lamports": sum(abs(x) for x in residuals),
            "transaction_fee_lamports": fee, "user_pays_transaction_fee": keys[0] == user,
            "user_system_outflows_lamports": outgoing, "user_system_inflows_lamports": incoming,
            "user_transaction_fee_lamports": user_fee,
            "user_observed_net_debit_lamports": -actual[positions[user]],
            "user_explained_net_debit_lamports": outgoing-incoming+user_fee,
            "parsed_system_move_count": len(moves)}, moves


def event_values(tx, record, layout):
    group = next(g for g in tx["meta"]["innerInstructions"] if g["index"] == record["parent_index"])
    raw = base.b58decode(group["instructions"][record["inner_index"]]["data"])[8:]
    if base.sha(raw) != record["payload_sha256"]:
        raise CaptureError("event-identity")
    definition = next(x for x in layout["events"] if x["name"] == record["kind"])
    return base.decode_event(raw, definition, layout)


def inspect_case(tx, prior, compared, layout):
    if prior["state"] == "unsupported-or-inconsistent-event-evidence":
        raise CaptureError("baseline-unsupported")
    creates = [e for e in prior["events"] if e["kind"] == "CreateEvent"]
    trades = [e for e in prior["events"] if e["kind"] == "TradeEvent"]
    if len(creates) != 1 or len(trades) > 1:
        raise CaptureError("single-creation-buy-scope")
    create = event_values(tx, creates[0], layout)
    if not trades:
        ledger, _ = cashflows(tx, create["user"])
        return {"state": "creation-only-accounting-consistent" if ledger["all_account_net_deltas_match"] else "accounting-mismatch",
                "trade_observed": False, "cashflows": ledger}
    if len(compared["trade_events"]) != 1 or compared["trade_events"][0]["candidate_state"] != "exact-layout-and-transfer-match-diagnostic-only":
        raise CaptureError("comparison-unsupported")
    trade = trades[0]
    values = event_values(tx, trade, layout)
    parent_index = trade["parent_index"]
    parent = tx["transaction"]["message"]["instructions"][parent_index]
    keys = {x["pubkey"] for x in tx["transaction"]["message"]["accountKeys"]}
    roles = base.account_roles(parent, "buy_v2", layout, keys)
    principal_roles = ("user", "bonding_curve", "creator_vault", "fee_recipient", "buyback_fee_recipient")
    if len({roles[k] for k in principal_roles}) != len(principal_roles):
        raise CaptureError("aliased-fee-roles")
    group = next(g for g in tx["meta"]["innerInstructions"] if g["index"] == parent_index)
    if trade["inner_index"] != len(group["instructions"])-1:
        raise CaptureError("event-not-final")
    if (create["is_cashback_enabled"] or create["is_holder_reward"] or values["shareholders"]
            or any(values[k] for k in ("cashback", "cashback_fee_basis_points", "holder_rewards", "holder_rewards_bps",
                                       "creator_fee_unclaimed", "quote_transfer_fee"))):
        raise CaptureError("unsupported-fee-mode")
    args = base.b58decode(parent["data"])
    if len(args) != 24:
        raise CaptureError("buy-arguments")
    amount, cap = (int.from_bytes(args[i:i+8], "little") for i in (8, 16))
    ledger, moves = cashflows(tx, roles["user"])
    buy_moves = [m for m in moves if m["parent"] == parent_index]
    if any(m["source"] != roles["user"] or type(m["stack_height"]) is not int or m["stack_height"] != 2 for m in buy_moves):
        raise CaptureError("unsupported-buy-move")
    def transfers(role):
        return [m["lamports"] for m in buy_moves if m["kind"] == "transfer" and m["destination"] == roles[role]]
    creator_transfers = transfers("creator_vault")
    recipient_transfers = transfers("fee_recipient")
    buyback_transfers = transfers("buyback_fee_recipient")
    sol, token, fee, creator_fee = (values[k] for k in ("sol_amount", "token_amount", "fee", "creator_fee"))
    fee_bps, creator_bps, buyback_bps = (values[k] for k in ("fee_basis_points", "creator_fee_basis_points", "buyback_fee_basis_points"))
    if any(x > 10000 for x in (fee_bps, creator_bps, buyback_bps)):
        raise CaptureError("fee-rate-range")
    # Arithmetic comparisons of reported values, not a certified fee schedule.
    ceil_bps = lambda value, bps: (value*bps+9999)//10000
    creator_matches = creator_transfers.count(creator_fee) if creator_fee else 0
    checks = {
        "event_recipient_matches_parent": values["fee_recipient"] == roles["fee_recipient"],
        "event_creator_matches_creation": values["creator"] == create["creator"],
        "event_mode_matches_creation": values["mayhem_mode"] == create["is_mayhem_mode"],
        "instruction_amount_matches_event": amount == token,
        "trade_and_reported_fees_within_instruction_cap": sol+fee+creator_fee <= cap,
        "reported_protocol_fee_matches_ceiling_arithmetic": fee == ceil_bps(sol, fee_bps),
        "reported_creator_fee_matches_ceiling_arithmetic": creator_fee == ceil_bps(sol, creator_bps),
        "reported_buyback_matches_split_arithmetic": values["buyback_fee"] == fee*buyback_bps//10000,
        "protocol_fee_matches_combined_recipient_transfers": len(recipient_transfers) <= 1 and len(buyback_transfers) <= 1 and sum(recipient_transfers)+sum(buyback_transfers) == fee,
        "buyback_matches_transfer": sum(buyback_transfers) == values["buyback_fee"],
        "creator_fee_has_unique_matching_transfer": creator_matches == 1 if creator_fee else not creator_transfers,
        "virtual_tokens_decrease_by_purchase": create["virtual_token_reserves"]-token == values["virtual_token_reserves"],
        "real_tokens_decrease_by_purchase": create["real_token_reserves"]-token == values["real_token_reserves"],
        "virtual_sol_increases_by_curve_transfer": create["virtual_sol_reserves"]+sol == values["virtual_sol_reserves"],
        "reported_real_sol_matches_first_curve_transfer": values["real_sol_reserves"] == sol,
        "native_quote_aliases_agree": create["virtual_quote_reserves"] == create["virtual_sol_reserves"] and values["virtual_quote_reserves"] == values["virtual_sol_reserves"] and values["real_quote_reserves"] == values["real_sol_reserves"],
    }
    observed_buy_outflows = sum(m["lamports"] for m in buy_moves)
    trade_total = sol+fee+creator_fee
    return {"state": "observed-accounting-consistent-live-blocked" if all(checks.values()) and ledger["all_account_net_deltas_match"] else "accounting-mismatch",
            "trade_observed": True, "checks": checks, "cashflows": ledger,
            "trade": {"curve_payment_lamports": sol, "protocol_fee_reported_lamports": fee,
                      "protocol_recipient_transfer_lamports": sum(recipient_transfers),
                      "buyback_transfer_lamports": sum(buyback_transfers),
                      "creator_fee_reported_lamports": creator_fee,
                      "creator_vault_transfers_lamports": creator_transfers,
                      "additional_creator_vault_lamports": sum(creator_transfers)-creator_fee if checks["creator_fee_has_unique_matching_transfer"] else None,
                      "trade_plus_reported_fees_lamports": trade_total,
                      "buy_parent_system_outflows_lamports": observed_buy_outflows,
                      "additional_buy_parent_outflows_lamports": observed_buy_outflows-trade_total,
                      "buy_parent_create_account_lamports": sum(m["lamports"] for m in buy_moves if m["kind"] == "createAccount"),
                      "instruction_max_cost_lamports": cap},
            "additional_transfer_purpose_verified": False, "rent_exemption_verified": False}


def inspect(report, bundle):
    compared = schema.compare(report, bundle)
    prior = base.inspect_bundle(report, bundle, base.schema())
    layout, _ = schema.candidate_layout()
    cases = []
    for candidate, p, c in zip(bundle["candidates"], prior["cases"], compared["cases"]):
        tx = next(e["response"]["result"] for e in bundle["rpc_evidence"] if e["method"] == "getTransaction" and e["params"][0] == candidate["signature"])
        try:
            result = inspect_case(tx, p, c, layout)
        except (CaptureError, ValueError, KeyError, TypeError, AttributeError, StopIteration, IndexError, RecursionError):
            result = {"state": "unsupported-or-inconsistent-accounting-evidence"}
        cases.append({"case": p["case"], **result})
    return {"schema_version": 1, "status": "offline-accounting-inspection-complete-live-blocked", "cases": cases,
            "profile_sha256": schema.PROFILE_SHA256, "network_used": False, "credentials_loaded": False,
            "transactions_sent": 0, "paid_collection_enabled": False, "fee_model_verified": False,
            "historical_fee_config_verified": False, "deployed_program_version_verified": False,
            "historical_curve_accounts_verified": False, "curve_reconstruction_accepted": False,
            "profitability_evaluated": False, "limitations": [
                "one creation and at most one direct native-SOL buy_v2 per transaction; other modes remain unsupported",
                "net cashflow agreement is internal consistency of saved provider evidence, not authenticated execution",
                "event reserve arithmetic is not a historical curve-account read or executable pricing model",
                "reported fee-rate arithmetic does not establish historical configuration or universal rounding rules",
                "additional creator-vault transfers retain unknown purpose; no rent or refundability assumption",
                "transaction debit includes creation/account funding and fees; it is not standalone repeat-trade cost"]}


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        for name in ("rpc-report", "evidence", "output"):
            parser.add_argument("--"+name, required=True)
        args = parser.parse_args(argv)
        output = Path(args.output)
        if output.exists() or output.is_symlink(): raise CaptureError("output-exists")
        pins = {n: base.sha((ROOT/n).read_bytes()) for n in SOURCES}
        report_raw = base.read_file(args.rpc_report, 128*1024)
        report = strict_json(report_raw)
        compressed = base.read_file(args.evidence, 16*1024*1024)
        if base.sha(compressed) != report.get("evidence_sha256"): raise CaptureError("checksum")
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle:
            raw = handle.read(base.MAX_INPUT+1)
        if len(raw) > base.MAX_INPUT or base.sha(raw) != report.get("evidence_decoded_sha256"):
            raise CaptureError("decoded-checksum-or-cap")
        result = inspect(report, strict_json(raw))
        if pins != {n: base.sha((ROOT/n).read_bytes()) for n in SOURCES}: raise CaptureError("source-changed")
        result.update(source_sha256=pins, rpc_report_sha256=base.sha(report_raw),
                      evidence_sha256=base.sha(compressed), evidence_decoded_sha256=base.sha(raw))
        with tempfile.TemporaryDirectory(prefix=".r1-accounting-", dir=output.parent) as tmp:
            prepared = Path(tmp)/"report.json"
            exclusive_file(prepared, (canonical(result)+"\n").encode())
            os.link(prepared, output, follow_symlinks=False)
        sync_dir(output.parent)
        print("R1 accounting inspection recorded; historical model and live acceptance remain blocked.")
        return 0
    except Exception:
        print("R1 accounting inspection stopped; no acceptance granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
