"""Fixed child: validates consumed admission, consumes sealed sentinel, runs session."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/'r1-data'))


def run(output, ipc, parent, fd):
    from supervisor_worker import bootstrap
    bootstrap(parent)
    import admission as ad
    import asyncio
    from contextlib import nullcontext, redirect_stderr
    import io
    import re
    import signal
    from unittest.mock import patch
    import credential
    import fixtures
    import session as s
    import archive as a
    import check_session
    from capture import CaptureError, digest, exclusive_file, Limits
    from provider_wire import Wire, secret_variants
    if (dict(os.environ) != ad.ENVIRONMENT or not sys.flags.ignore_environment
            or not sys.flags.no_user_site or not sys.dont_write_bytecode):
        raise CaptureError('admission-worker-environment')
    output, ipc = Path(output), Path(ipc)
    request, raw = ad.load_request(output)
    if request['parent_pid'] != parent: raise CaptureError('admission-worker-parent')
    secret = credential.consume(fd)
    if not re.fullmatch('R1-SYNTHETIC-[0-9a-f]{32}', secret):
        raise CaptureError('admission-synthetic-required')
    mode = request['scenario']
    if mode in ('stall', 'tainted-diagnostic'):
        exclusive_file(output/'fault-ready.json', s.json_bytes({
            'request_sha256':digest(raw), 'fault':mode, 'credential_descriptor_closed':True}))
    if mode == 'stall':
        # One bounded fault injection. The inherited alarm/parent deadline reaps it.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        while True: signal.pause()
    log = io.StringIO()
    with redirect_stderr(log):
        if mode == 'tainted-diagnostic':
            print('RuntimeWarning: '+secret, file=sys.stderr)
        else:
            peer = fixtures.Peer(mode, 4)
            async def factory():
                if mode != 'idle': peer.frames.put_nowait(peer.event('create'))
                return Wire(peer, secret_variants(secret))
            with patch.object(s, 'Server', fixtures.TestServer) if request['development_endpoint'] else nullcontext():
                asyncio.run(s.run(output/'control', ipc, factory, Limits(**request['limits'])))
            if not peer.closed: raise CaptureError('admission-worker-close')
        if check_session.DIAGNOSTIC.search(log.getvalue()):
            raise CaptureError('admission-worker-diagnostic')
        exported = a.export(output/'control', output/'export')
    if check_session.DIAGNOSTIC.search(log.getvalue()):
        raise CaptureError('admission-worker-diagnostic')
    if ad.load_request(output)[1] != raw: raise CaptureError('admission-worker-changed')
    receipt = {'schema_version': 1, 'request_sha256': digest(raw),
               'contract_sha256': request['contract_sha256'],
               'archive_sha256': exported['archive_sha256'],
               'session_admission_sha256': digest(ad.read_private(output/'control/admission.json',65536)),
               'credential_descriptor_closed': True, 'diagnostics_clean': True,
               'internet_and_dns_blocked': True, 'child_process_creation_blocked': True,
               'parent_death_sigkill': True, 'resources': ad.RESOURCES,
               'provider_connection_opened': False, 'real_credential_used': False,
               'live_launch_authorized': False}
    exclusive_file(output/'worker-result.json', s.json_bytes(receipt))


if __name__ == '__main__':
    try:
        if len(sys.argv) != 5: raise RuntimeError('admission-worker-arguments')
        run(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    except BaseException:
        sys.exit(1)
