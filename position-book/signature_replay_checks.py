"""Exact-byte verification reuse against public signed fixtures; no keys or RPC."""
import base64
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import patch
import wire


def fixture(name='existing'):
    return json.loads(Path(wire.__file__).with_name('public-fixtures.json').read_text())[name]['signedTransactionBase64']


def refused(fn):
    try: fn()
    except ValueError: return
    raise AssertionError('invalid signature or encoding accepted')


def run():
    cases={};encoded=fixture();original=wire.subprocess.run
    with patch('socket.socket',side_effect=AssertionError('network')):
        with patch.object(wire.subprocess,'run',wraps=original) as calls:
            expected=wire.verify_wire(encoded);wire.verify_wire(encoded)
            assert calls.call_count==2
            cases['ordinary-verifier-remains-uncached']='passed'
            with wire.signature_verification_scope() as stats:
                a=wire.verify_wire(encoded);b=wire.verify_wire(encoded)
                assert a==b==expected and stats()['verifierProcesses']==1 and stats()['memoHits']==1
                cases['identical-wire-reuses-only-successful-signature-check']='passed'
                a['signatures'][0]='changed-return-value'
                assert wire.verify_wire(encoded)==expected
                cases['returned-proof-mutation-cannot-poison-reuse']='passed'
                raw=base64.b64decode(encoded)
                for offset in (1,len(raw)-1):
                    changed=bytearray(raw);changed[offset]^=1
                    bad=base64.b64encode(changed).decode()
                    before=stats()['verifierProcesses']
                    refused(lambda:wire.verify_wire(bad));refused(lambda:wire.verify_wire(bad))
                    assert stats()['verifierProcesses']==before+2
                cases['changed-message-or-signature-is-reverified-and-rejected']='passed'
                cases['negative-verification-is-never-memoized']='passed'
                before=stats()['verificationCalls']
                refused(lambda:wire.verify_wire(encoded+'\n'))
                assert stats()['verificationCalls']==before
                cases['parsing-and-canonical-encoding-still-run-before-reuse']='passed'
                outer_hits=stats()['memoHits']
                with wire.signature_verification_scope() as nested:
                    wire.verify_wire(encoded);assert nested()['verifierProcesses']==1
                wire.verify_wire(encoded);assert stats()['memoHits']==outer_hits+1
                assert nested()['memoEntries']==0
                cases['nested-scope-is-isolated-and-cleared']='passed'
            assert stats()['memoEntries']==0
            with wire.signature_verification_scope() as fresh:
                wire.verify_wire(encoded);assert fresh()['verifierProcesses']==1
            cases['new-operation-reverifies-and-old-scope-clears']='passed'
        try:
            with wire.signature_verification_scope() as failed:
                wire.verify_wire(encoded);raise RuntimeError('stop operation')
        except RuntimeError:pass
        assert failed()['memoEntries']==0 and wire._SIGNATURE_SCOPE.get() is None
        cases['exception-clears-verification-scope']='passed'
        # Small substituted cap exercises the same full-cap fallback without
        # manufacturing a large collection of signatures or reading any keys.
        with patch.object(wire,'MAX_SIGNATURE_MEMO',1),wire.signature_verification_scope() as stats:
            wire.verify_wire(encoded)
            other=fixture('create');wire.verify_wire(other);wire.verify_wire(other)
            assert stats()['memoEntries']==1 and stats()['capacityBypasses']==2 and stats()['verifierProcesses']==3
        cases['full-memo-falls-back-to-real-verification']='passed'
        with wire.signature_verification_scope():
            multi=fixture('multisigner');wire.verify_wire(multi)
            raw=bytearray(base64.b64decode(multi));raw[65]^=1
            refused(lambda:wire.verify_wire(base64.b64encode(raw).decode()))
        cases['all-required-signatures-remain-bound']='passed'
    return cases
