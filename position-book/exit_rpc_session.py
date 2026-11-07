"""Collection-scoped HTTPS reuse for the fixed public devnet exit reader.

No redirects, proxy/environment configuration, credentials, retries or sender.
An incomplete/failed exchange poisons this session; it is never replayed.
"""
import http.client
import json
import math
import ssl
import time
import urllib.error

ENDPOINT = 'https://api.devnet.solana.com'
METHODS = frozenset(('getGenesisHash', 'getMultipleAccounts', 'getBlockTime',
    'getLatestBlockhash', 'isBlockhashValid', 'getFeeForMessage', 'simulateTransaction'))
MAX_RESPONSE = 4 * 1024 * 1024


class Session:
    def __init__(self, *, monotonic=time.monotonic):
        self.monotonic = monotonic
        self.connection = None
        self.active = False
        self.closed = False
        self.calls = 0
        self.connections = 0
        self.completed = 0
        self.context = ssl.create_default_context()

    def _disconnect(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def close(self):
        self.closed = True
        self._disconnect()

    def open(self, request, timeout):
        if self.closed or self.active or self.calls >= 20:
            raise ValueError('exit-rpc-session-unavailable')
        if (request.full_url != ENDPOINT or request.get_method() != 'POST' or
                not isinstance(request.data, bytes) or len(request.data) > 65536):
            raise ValueError('exit-rpc-session-request')
        body = json.loads(request.data)
        if (not isinstance(body, dict) or body.get('method') not in METHODS or
                type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 10):
            raise ValueError('exit-rpc-session-request')
        deadline = self.monotonic() + timeout
        self.calls += 1
        self.active = True
        try:
            if self.connection is None:
                self.connection = http.client.HTTPSConnection('api.devnet.solana.com',
                    timeout=timeout, context=self.context)
                self.connections += 1
            self.connection.timeout = timeout
            if self.connection.sock is not None:
                self.connection.sock.settimeout(timeout)
            # Ignore all caller-supplied headers (including Authorization/Host).
            self.connection.request('POST', '/', body=request.data,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                         'Accept-Encoding': 'identity'})
            response = self.connection.getresponse()
            if response.status != 200:
                code = response.status
                response.close()
                self.close()
                # HTTPError owns an empty file wrapper even when fp=None.
                # Consumers only need the status; close that wrapper before
                # raising so Python 3.14 does not rely on implicit cleanup.
                error = urllib.error.HTTPError(ENDPOINT, code, 'devnet-http-error', {}, None)
                error.close()
                raise error
            return Response(self, response, deadline)
        except urllib.error.HTTPError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            self.close()
            raise urllib.error.URLError('devnet-connection-failed') from exc
        except BaseException:
            self.close()
            raise

    def summary(self):
        return dict(version='exit-rpc-session-1', requests=self.calls,
                    connectionsOpened=self.connections, completedResponses=self.completed,
                    closed=self.closed, retries=0)


class Response:
    def __init__(self, session, response, deadline):
        self.session, self.response, self.deadline = session, response, deadline
        self.read_once = False
        self.complete = False

    def __enter__(self):
        return self

    def read(self, size):
        if self.read_once or type(size) is not int or not 0 < size <= MAX_RESPONSE + 1:
            self.session.close()
            raise ValueError('exit-rpc-response-read')
        self.read_once = True
        try:
            chunks = []; total = 0
            while total < size:
                remaining = self.deadline - self.session.monotonic()
                if remaining <= 0:
                    raise TimeoutError('exit-rpc-response-expired')
                connection = self.session.connection
                if connection is not None and connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = self.response.read1(min(65536, size-total))
                if self.session.monotonic() >= self.deadline:
                    raise TimeoutError('exit-rpc-response-expired')
                chunks.append(chunk); total += len(chunk)
                if not chunk or self.response.isclosed():
                    if self.response.length not in (None, 0):
                        raise http.client.IncompleteRead(b'')
                    break
            raw = b''.join(chunks)
            self.complete = self.response.isclosed() and len(raw) <= MAX_RESPONSE
            if not self.complete:
                self.session.close()
            return raw
        except (OSError, http.client.HTTPException) as exc:
            self.session.close()
            raise urllib.error.URLError('devnet-response-failed') from exc
        except BaseException:
            self.session.close()
            raise

    def __exit__(self, typ, value, traceback):
        try:
            if typ is not None or not self.complete:
                self.session.close()
            else:
                self.session.completed += 1
                if self.response.will_close:
                    # A later logical request may establish a new connection.
                    # The completed request is never retried.
                    self.session._disconnect()
        finally:
            self.response.close()
            self.session.active = False
