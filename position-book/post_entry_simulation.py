"""Opt-in nine-account unsigned entry simulation; one response, no sender."""
from copy import deepcopy
import json
import unsigned_simulation as base
import post_entry
from core import check
from contract import digest
from recorded_capture import GENESIS
VERSION = base.VERSION


class Transport(base.Transport):
    def arm(self, packet, capture, now_ms):
        super().arm(packet,capture,now_ms)
        self.expected = post_entry.parameters(packet,capture)

    def open(self, request, timeout):
        if len(self.calls) == 18:
            body = json.loads(request.data)
            check(hasattr(self,'expected') and digest(body.get('params')) == digest(self.expected),
                  'post-entry-request-mismatch')
        return super().open(request,timeout)


class SimulationRpc(base.SimulationRpc):
    ACCOUNT_COUNT = 9


def collect(packet, capture, price, *, transport, clock, deadline, _evidence_sink=None):
    start = clock()
    result = dict(state='unavailable',requestedAtMs=start,signatureVerification=False,
        transactionsSent=0,signaturesCreated=0,executionApproved=False,
        postEntryPoolReviewed=False)
    try:
        check(type(transport) is Transport, 'post-entry-transport')
        check(start < deadline, 'simulation-evidence-expired')
        transport.arm(packet,capture,start)
        rpc = SimulationRpc(transport)
        item = rpc.request('simulateTransaction',post_entry.parameters(packet,capture))
        received = clock();result['receivedAtMs'] = received
        check(start <= received < deadline, 'simulation-evidence-expired')
        check(item['state'] == 'received', 'simulation-rpc-unavailable')
        # The ninth account is retained in the private handoff. Existing entry
        # effect validation stays exact for its original eight-account contract.
        entry = deepcopy(item)
        rows = entry['result']['value']['accounts']
        check(len(rows) == 9, 'post-entry-account-count');rows.pop()
        result.update(base.review(packet,capture,price,entry,now_ms=received))
        result['fullSimulationEvidenceSha256'] = digest(item)
        result['requestParametersSha256'] = digest(transport.expected)
        genesis = rpc.request('getGenesisHash',[])
        check(genesis.get('state') == 'received' and genesis.get('result') == GENESIS['devnet'],
              'simulation-cluster')
        finish = clock();check(received <= finish < deadline,'simulation-evidence-expired')
        result['finishedAtMs'] = finish
        if _evidence_sink is not None:_evidence_sink(deepcopy(item))
    except (ValueError,KeyError,TypeError,IndexError):
        result.update(state='unavailable',reason='post-entry-simulation-unavailable')
    return result
