"""Real HTTP framing over disposable socketpairs; no network or TLS bypass in production."""
import http.client
import json
from pathlib import Path
import socket
import ssl
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import exit_rpc_session as m

SOCKET_CLASS = socket.socket


def request(method='getGenesisHash', url=m.ENDPOINT):
    return urllib.request.Request(url, method='POST', data=json.dumps({
        'jsonrpc':'2.0','id':1,'method':method,'params':[]}).encode(),
        headers={'Authorization':'must-not-forward', 'Host':'must-not-forward'})


class Wire:
    def __init__(self, responses):
        self.responses=list(responses); self.requests=[]; self.created=[]; self.threads=[]

    def factory(self, host, *, timeout, context):
        self.created.append((host,timeout,context))
        owner=self
        class Connection(http.client.HTTPConnection):
            def connect(self):
                # Fixture blocks network sockets; restore only around AF_UNIX socketpair.
                with patch.object(socket, 'socket', SOCKET_CLASS):
                    self.sock, peer=socket.socketpair()
                self.sock.settimeout(self.timeout)
                def serve():
                    try:
                        with peer, peer.makefile('rb') as stream:
                            while owner.responses:
                                first=stream.readline()
                                if not first:return
                                headers={}
                                while True:
                                    line=stream.readline()
                                    if line==b'\r\n':break
                                    if not line:return
                                    k,v=line.decode().strip().split(':',1);headers[k.lower()]=v.strip()
                                body=stream.read(int(headers['content-length']))
                                owner.requests.append((first,headers,body))
                                response=owner.responses.pop(0)
                                if callable(response):response=response(body)
                                if response is None:return
                                peer.sendall(response)
                                if b'Connection: close' in response:return
                    except (OSError,ValueError):pass
                thread=threading.Thread(target=serve,daemon=True);owner.threads.append(thread);thread.start()
        return Connection(host,timeout=timeout)

    def finish(self):
        for thread in self.threads:
            thread.join(2)
            if thread.is_alive():raise AssertionError('test socket left open')


def reply(body=b'{"jsonrpc":"2.0","id":1,"result":"ok"}', *, status=200, close=False, length=None):
    return (f'HTTP/1.1 {status} Test\r\nContent-Length: {len(body) if length is None else length}\r\n'+
            ('Connection: close\r\n' if close else '')+'\r\n').encode()+body


class SessionTests(unittest.TestCase):
    def exchange(self, session):
        with session.open(request(),timeout=2) as response:
            return response.read(m.MAX_RESPONSE+1)

    def test_twenty_requests_reuse_one_socket_with_verified_tls_configuration(self):
        wire=Wire([reply()]*20)
        with patch.object(m.http.client,'HTTPSConnection',wire.factory):
            session=m.Session()
            try:
                for _ in range(20):self.assertEqual(json.loads(self.exchange(session))['result'],'ok')
                with self.assertRaises(ValueError):self.exchange(session)
            finally:session.close()
        wire.finish()
        self.assertEqual(len(wire.created),1);self.assertEqual(len(wire.requests),20)
        host,_,context=wire.created[0]
        self.assertEqual(host,'api.devnet.solana.com')
        self.assertTrue(context.check_hostname);self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        for line,headers,_ in wire.requests:
            self.assertEqual(line,b'POST / HTTP/1.1\r\n')
            self.assertNotIn('authorization',headers);self.assertNotIn('proxy-authorization',headers)
            self.assertEqual(headers['host'],'api.devnet.solana.com')
        self.assertEqual(session.summary()['completedResponses'],20)

    def test_server_close_allows_next_request_not_replay(self):
        wire=Wire([reply(close=True),reply()])
        with patch.object(m.http.client,'HTTPSConnection',wire.factory):
            session=m.Session()
            try:self.exchange(session);self.exchange(session)
            finally:session.close()
        wire.finish();self.assertEqual(len(wire.created),2);self.assertEqual(len(wire.requests),2)

    def test_redirect_and_http_errors_are_not_followed_or_retried(self):
        for status in (301,302,307,400,429,503):
            wire=Wire([reply(status=status)])
            with patch.object(m.http.client,'HTTPSConnection',wire.factory):
                session=m.Session()
                with self.assertRaises(urllib.error.HTTPError) as caught:self.exchange(session)
                self.assertEqual(caught.exception.code,status)
                self.assertTrue(caught.exception.closed)
                self.assertTrue(caught.exception.fp.closed)
                with self.assertRaises(ValueError):self.exchange(session)
            wire.finish();self.assertEqual(len(wire.requests),1)

    def test_closed_http_error_preserves_collector_status_without_provider_body(self):
        import admission_exit_capture  # Establish the existing collector import paths.
        from recorded_capture import Client
        wire=Wire([reply(body=b'private-provider-detail',status=429)])
        with patch.object(m.http.client,'HTTPSConnection',wire.factory):
            session=m.Session()
            result=Client('devnet',opener=session).request('getGenesisHash',[])
        wire.finish()
        self.assertEqual(result,{'state':'http-error','httpStatus':429})
        self.assertTrue(session.closed)
        self.assertEqual(len(wire.requests),1)

    def test_connection_loss_and_truncated_response_poison_session(self):
        for response in (None,reply(close=True,length=999)):
            wire=Wire([response])
            with patch.object(m.http.client,'HTTPSConnection',wire.factory):
                session=m.Session()
                with self.assertRaises(urllib.error.URLError):self.exchange(session)
                with self.assertRaises(ValueError):self.exchange(session)
            wire.finish();self.assertEqual(len(wire.requests),1)

    def test_oversized_partial_and_unread_responses_cannot_be_reused(self):
        for mode in ('large','partial','unread'):
            wire=Wire([reply(body=b'x'*(m.MAX_RESPONSE+2) if mode=='large' else b'abcdef')])
            with patch.object(m.http.client,'HTTPSConnection',wire.factory):
                session=m.Session()
                with session.open(request(),timeout=2) as response:
                    if mode=='large':self.assertEqual(len(response.read(m.MAX_RESPONSE+1)),m.MAX_RESPONSE+1)
                    elif mode=='partial':self.assertEqual(response.read(1),b'a')
                with self.assertRaises(ValueError):self.exchange(session)
            wire.finish()

    def test_chunked_framing_is_bounded_and_reusable_only_after_terminator(self):
        chunked=b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n'
        wire=Wire([chunked,reply()])
        with patch.object(m.http.client,'HTTPSConnection',wire.factory):
            session=m.Session()
            try:
                self.assertEqual(self.exchange(session),b'abc')
                self.exchange(session)
            finally:session.close()
        wire.finish();self.assertEqual(len(wire.created),1)
        wire=Wire([b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\nXYZ\r\n'])
        with patch.object(m.http.client,'HTTPSConnection',wire.factory):
            session=m.Session()
            with self.assertRaises(urllib.error.URLError):self.exchange(session)
            self.assertTrue(session.closed)
        wire.finish()

    def test_deadline_during_response_rejects_and_closes(self):
        wire=Wire([reply()]);clock=[0]
        with patch.object(m.http.client,'HTTPSConnection',wire.factory):
            session=m.Session(monotonic=lambda:clock[0])
            with session.open(request(),timeout=2) as response:
                clock[0]=2
                with self.assertRaises(urllib.error.URLError):response.read(m.MAX_RESPONSE+1)
            self.assertTrue(session.closed)
        wire.finish()

    def test_unsafe_requests_never_connect_and_reentrant_read_is_rejected(self):
        with patch.object(m.http.client,'HTTPSConnection') as factory:
            session=m.Session()
            for req in (request('sendTransaction'),request('requestAirdrop'),request(url=m.ENDPOINT+'/'),request(url='http://api.devnet.solana.com')):
                with self.assertRaises(ValueError):session.open(req,timeout=2)
            for timeout in (0,-1,11,float('nan'),True):
                with self.assertRaises(ValueError):session.open(request(),timeout=timeout)
            factory.assert_not_called()
        wire=Wire([reply()])
        with patch.object(m.http.client,'HTTPSConnection',wire.factory):
            session=m.Session()
            with session.open(request(),timeout=2) as response:
                with self.assertRaises(ValueError):session.open(request(),timeout=2)
                with self.assertRaises(ValueError):response.read(-1)
        wire.finish();self.assertTrue(session.closed)

    def test_connected_collector_default_session_preserves_proof_and_stops_on_expiry(self):
        from copy import deepcopy
        import admission_exit_capture_checks as c
        for mode in ('complete','expired','stop'):
            with c.case() as case:
                c.settle(case);c.apply(case)
                first,e,baseline=c.setup(case);rpc=c.Opener(first,e);clock=c.Clock();items=[]
                def response(body,row,index):
                    if index==10:
                        if mode=='expired':clock.at+=10001
                        elif mode=='stop':(case.home/'STOP').touch(mode=0o600)
                    return reply(json.dumps(dict(jsonrpc='2.0',id=json.loads(body)['id'],result=row)).encode())
                wire=Wire([lambda body,row=row,index=index:response(body,row,index)
                           for index,row in enumerate(rpc.rows,1)])
                def read(*args):
                    row=deepcopy(case.e['costInputs']['reservations'])
                    row.update(readStartedAtMs=clock(),observedAtMs=clock());return row
                old=case.path.read_bytes()
                with patch.object(m.http.client,'HTTPSConnection',wire.factory),patch.object(c.m.exit,'BASELINE',baseline),patch.object(c.m.view,'read_locked',side_effect=read):
                    result=c.m.collect(case.home,case.wallet,case.pool,clock=clock,
                                       monotonic=lambda:0,_evidence_sink=items.append)
                wire.finish()
                self.assertEqual(case.path.read_bytes(),old)
                self.assertTrue(result['rpcSession']['closed'])
                self.assertEqual(result['rpcSession']['connectionsOpened'],1)
                if mode=='complete':
                    self.assertEqual(result['state'],'exit-evidence-collected-research-only',result)
                    self.assertEqual(result['requestMethods'],c.m.METHODS)
                    self.assertEqual(result['rpcSession']['completedResponses'],20)
                    self.assertEqual(len(items),1)
                    self.assertEqual(result['provenance']['evidenceSha256'],c.m.digest(items[0]['evidence']))
                else:
                    self.assertEqual(result['state'],'unavailable');self.assertEqual(items,[])
                    self.assertEqual(len(wire.requests),10)
                    # Nested packet validation may sanitize the refusal before
                    # another transport call. The gate is no eleventh request
                    # and no private evidence handoff, not a diagnostic spelling.
                    self.assertIsNotNone(result['diagnosticCode'])


if __name__=='__main__':unittest.main()
