"""Disposable cryptographic fixture; no user keys, live HTTP or retained secrets."""
import base64
from contextlib import contextmanager
import json
import subprocess
from unittest.mock import patch

import admission_submission_checks as entry
import locked_admission_checks as locked
import admission_exit_collection_checks as collected
import exit_signing_handoff as signing
import restricted_exit_signer as backend
from entry_accounting_checks import collect,apply
from fresh_packet import message
from wire import b58
from core import write_new


def sign(key,packet):
    msg=base64.b64decode(packet['unsignedTransactionBase64'],validate=True)[65:]
    js="const c=require('node:crypto'),fs=require('node:fs'),v=JSON.parse(fs.readFileSync(0));const k=c.createPrivateKey({key:Buffer.from(v.key,'base64'),format:'der',type:'pkcs8'}),m=Buffer.from(v.message,'base64');process.stdout.write(Buffer.concat([Buffer.from([1]),c.sign(null,m,k),m]).toString('base64'));"
    r=subprocess.run(['node','-e',js],input=json.dumps(dict(key=key,message=base64.b64encode(msg).decode())),
                     text=True,capture_output=True,check=True,timeout=5)
    return r.stdout


@contextmanager
def signed_case():
    js="const c=require('node:crypto'),k=c.generateKeyPairSync('ed25519');process.stdout.write(JSON.stringify({key:k.privateKey.export({format:'der',type:'pkcs8'}).toString('base64'),public:k.publicKey.export({format:'der',type:'spki'}).subarray(12).toString('base64')}));"
    keys=json.loads(subprocess.run(['node','-e',js],text=True,capture_output=True,check=True,timeout=5).stdout)
    key=keys.pop('key');wallet=b58(base64.b64decode(keys['public']))
    e,p=locked.raw_fixture();scope=p['scope'];scope['accounts']['wallet']=wallet
    msg=message(scope,e['costInputs']['packet']['policy']['blockhash'])
    unsigned=base64.b64encode(b'\x01'+bytes(64)+msg).decode()
    packet=dict(unsignedTransactionBase64=unsigned)
    fixture=dict(wallet=wallet,unsignedTransactionBase64=unsigned,signedTransactionBase64=sign(key,packet))
    try:
        with patch.object(entry,'fixture',side_effect=lambda:locked.fixture(fixture)),entry.case() as c:
            collect(c);apply(c);e,proof,baseline=collected.collected(c);collected.prepare(c,e,proof,baseline)
            with patch.object(signing.preparation,'BASELINE',baseline),patch.object(signing.view,'read_locked',return_value=c.e['costInputs']['reservations']):
                c.exit_wire=sign(key,e['packet'])
                signing.dispatch(c.home,c.wallet,c.pool,signer_adapter=lambda _:c.exit_wire,clock=lambda:c.now)
                b=c.book()
                try:
                    from exit_submission import ExitSubmission
                    c.exit_state=ExitSubmission(b).signing()
                    row=b.db.execute('SELECT hash,at_ms FROM admission_exit_signing WHERE seq=1').fetchone()
                    write_new(c.path.parent/backend.ATTEMPT,dict(format='exit-signer-attempt-1',requestSha256=c.exit_state['requestSha256'],
                        signingHeadSha256=row['hash'],preparationSha256=c.exit_state['request']['preparationSha256'],atMs=row['at_ms']))
                    write_new(c.path.parent/backend.ACK,dict(format='exit-signer-ack-1',requestSha256=c.exit_state['requestSha256'],
                        signedTransactionBase64=c.exit_wire,wireSha256=c.exit_state['signed']['wireSha256']))
                finally:b.close()
                c.sign_successor=lambda request:sign(key,request['packet'])
                yield c
    finally:
        key=None
