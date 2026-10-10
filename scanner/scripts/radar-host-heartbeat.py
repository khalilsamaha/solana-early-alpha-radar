#!/usr/bin/env python3
"""Host-side Solana Radar readiness heartbeat; Python standard library only.

Configure interactively with --configure, then run once per minute via cron.
No success ping is sent unless the local /readyz response is HTTP 200 and
contains JSON {"ready": true}. No API keys or market data are sent externally.
--verify-backup PATH checks a copied SQLite backup without modifying it.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

CONFIG = Path.home() / ".config/solana-radar/heartbeat-url"
READY_URL = "http://127.0.0.1:8787/readyz"
PING_PATTERN = re.compile(
    r"https://hc-ping\.com/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, timeout):
    # Direct requests; never send localhost readiness checks through a proxy.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(url, timeout=timeout) as response:
        return response.status, response.read(65537)


def configure():
    if not sys.stdin.isatty():
        raise ValueError("Run --configure directly in an interactive terminal.")
    url = getpass.getpass("Paste the Healthchecks UUID ping URL (hidden): ").strip()
    if not PING_PATTERN.fullmatch(url):
        raise ValueError("Use the base https://hc-ping.com/<UUID> URL, without a suffix.")
    CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix=".heartbeat-", dir=CONFIG.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(url + "\n")
        os.replace(temporary, CONFIG)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Private ping URL saved. No ping sent during configuration.")


def heartbeat():
    try:
        url = CONFIG.read_text().strip()
        if not PING_PATTERN.fullmatch(url):
            raise ValueError()
    except (OSError, ValueError):
        print("Missing or invalid ping URL. Run --configure.", file=sys.stderr)
        return 2
    try:
        status, raw = fetch(READY_URL, 5)
        body = json.loads(raw)
        if status != 200 or not isinstance(body, dict) or body.get("ready") is not True:
            raise ValueError()
    except Exception:
        print("Radar is not ready; success heartbeat withheld.", file=sys.stderr)
        return 1
    try:
        status, raw = fetch(url, 10)
        # Healthchecks can return 200 with 'OK (not found)' for an invalid UUID.
        if status != 200 or raw.strip() != b"OK":
            raise ValueError()
    except Exception:
        print("External heartbeat was not acknowledged. Check connectivity and check URL.", file=sys.stderr)
        return 1
    print("Radar ready; Healthchecks acknowledged heartbeat.")
    return 0


def verify_backup(filename):
    path = Path(filename).resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        results = [row[0] for row in db.execute("PRAGMA integrity_check")]
        if results != ["ok"]:
            raise ValueError("SQLite integrity check failed.")
        candidates = db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        events = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    print("Backup integrity: OK")
    print(f"Stored candidates: {candidates}; stored events: {events}")
    print(f"Backup file: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--configure", action="store_true")
    group.add_argument("--verify-backup", metavar="PATH")
    args = parser.parse_args()
    try:
        if args.configure:
            configure()
        elif args.verify_backup:
            verify_backup(args.verify_backup)
        else:
            return heartbeat()
    except Exception as error:
        # Do not print exception messages: network errors can contain secret URLs.
        print(f"Operation failed ({type(error).__name__}); check inputs and permissions.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
