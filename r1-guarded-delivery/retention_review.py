"""Offline review of R1B lifecycle rules and optional owner-supplied destination evidence."""
import argparse
import json
from pathlib import Path
import sys

BUCKET = "solana-radar-backups-redeye-2026"
PREFIX = "r1-pilot-evidence/"
DAYS = 90
HIDE = "daysFromUploadingToHiding"
DELETE = "daysFromHidingToDeleting"
CANCEL = "daysFromStartingToCancelingUnfinishedLargeFiles"
ATTESTATIONS = (
    "bucket_private", "object_lock_settings_reviewed", "writer_can_create_unique_objects",
    "independent_reader_can_restore_version_by_id", "no_manual_hide_or_overwrite_before_owner_release",
    "zero_incremental_cost_for_operations_and_retention",
)


def read_json(stream):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    raw = stream.read(262145)
    if len(raw) > 262144:
        raise ValueError("input too large")
    return json.loads(raw, object_pairs_hook=unique)


def lifecycle(rules):
    """A descendant prefix can add a rule, so evaluate each distinct matching boundary."""
    if not isinstance(rules, list) or len(rules) > 100:
        raise ValueError("expected a B2 lifecycle rule array")
    relevant = []
    boundaries = {PREFIX}
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("fileNamePrefix"), str):
            raise ValueError("invalid lifecycle prefix")
        prefix = rule["fileNamePrefix"]
        if not (PREFIX.startswith(prefix) or prefix.startswith(PREFIX)):
            continue
        if set(rule) - {"fileNamePrefix", HIDE, DELETE, CANCEL}:
            raise ValueError("unrecognized matching rule")
        limits = [rule.get(field) for field in (HIDE, DELETE, CANCEL)]
        if all(v is None for v in limits) or any(v is not None and (type(v) is not int or v <= 0) for v in limits):
            raise ValueError("invalid matching rule limits")
        relevant.append(rule)
        if prefix.startswith(PREFIX):
            boundaries.add(prefix)
    profiles = []
    for prefix in sorted(boundaries):
        matches = [r for r in relevant if prefix.startswith(r["fileNamePrefix"])]
        effective = {k: min((r[k] for r in matches if r.get(k) is not None), default=None)
                     for k in (HIDE, DELETE, CANCEL)}
        if effective not in profiles:
            profiles.append(effective)
    return len(relevant), profiles


def assess(rules, facts):
    count, profiles = lifecycle(rules)
    if not isinstance(facts, dict):
        raise ValueError("expected redacted destination evidence")
    missing = []
    conflicts = []
    for key, expected in (("bucket", BUCKET), ("prefix", PREFIX)):
        if facts.get(key) is None:
            missing.append(key)
        elif facts[key] != expected:
            conflicts.append(key)
    for key in ATTESTATIONS:
        value = facts.get(key)
        if value is None:
            missing.append(key)
        elif value is not True:
            conflicts.append(key)
    sizes = {}
    for key in ("final_manifest_bytes", "available_storage_bytes", "included_retrieval_bytes"):
        value = facts.get(key)
        if value is None:
            missing.append(key)
        elif type(value) is not int or value < (1 if key == "final_manifest_bytes" else 0):
            conflicts.append(key)
        else:
            sizes[key] = value
    batch = sizes.get("final_manifest_bytes")
    if batch is not None:
        if "available_storage_bytes" in sizes and sizes["available_storage_bytes"] < batch:
            conflicts.append("insufficient-storage")
        if "included_retrieval_bytes" in sizes and sizes["included_retrieval_bytes"] < 2 * batch:
            conflicts.append("insufficient-allowance-for-two-full-restores")
    for profile in profiles:
        hide, delete = profile[HIDE], profile[DELETE]
        if hide is not None and delete is not None:
            # Even deletion after day 90 could preempt an open hold or owner review.
            key = "automatic-deletion-by-day-90" if hide + delete <= DAYS else "automatic-deletion-before-owner-release-possible"
            if key not in conflicts:
                conflicts.append(key)
    return {"status": "hold" if missing or conflicts else "reported-preflight-conditions-met",
            "matching_rules": count, "effective_rule_profiles": profiles, "missing_evidence": missing,
            "conflicts": conflicts, "live_account_verified": False, "retention_verified": False,
            "upload_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, help="optional private JSON with redacted, reviewed facts")
    args = parser.parse_args()
    try:
        rules = read_json(sys.stdin.buffer)
        facts = {}
        if args.review is not None:
            with args.review.open("rb") as stream:
                facts = read_json(stream)
        report = assess(rules, facts)
    except (ValueError, OSError, RecursionError):
        report = {"status": "hold", "reason": "invalid-or-unavailable-input", "upload_authorized": False}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "reported-preflight-conditions-met" else 2


if __name__ == "__main__":
    raise SystemExit(main())
