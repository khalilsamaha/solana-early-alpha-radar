import asyncio
import os
from pathlib import Path
import struct
import tempfile
import unittest

from capture import CaptureError
from shared_discovery import Server
from shared_owner import Owner


class Peer:
    def __init__(self, uid): self.uid = uid
    def getsockopt(self, *args): return struct.pack('3i', os.getpid(), self.uid, os.getgid())


class Writer:
    def __init__(self, uid): self.peer, self.closed = Peer(uid), False
    def get_extra_info(self, name): return self.peer
    def close(self): self.closed = True
    async def wait_closed(self): pass
    def write(self, raw): pass
    async def drain(self): pass


class Reader:
    async def read(self, size): return b''


class SharedDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='r1-ipc-test-')
        self.directory = Path(self.temp.name)
        async def forbidden(): raise AssertionError('must not open upstream')
        self.owner = Owner(forbidden)
        self.server = Server(self.owner, self.directory)

    async def asyncTearDown(self):
        await self.server.close()
        await self.owner.close()
        self.temp.cleanup()

    async def test_existing_endpoint_is_preserved_and_never_unlinked(self):
        self.server.path.write_bytes(b'preserve')
        with self.assertRaises(CaptureError): await self.server.start()
        self.assertEqual(self.server.path.read_bytes(), b'preserve')

    async def test_nonprivate_directory_is_rejected_before_bind(self):
        self.directory.chmod(0o755)
        with self.assertRaises(CaptureError): await self.server.start()
        self.assertFalse(self.server.path.exists())

    async def test_symlink_endpoint_is_preserved(self):
        target = self.directory / 'target'
        target.write_bytes(b'preserve')
        self.server.path.symlink_to(target)
        with self.assertRaises(CaptureError): await self.server.start()
        self.assertTrue(self.server.path.is_symlink())

    async def test_wrong_uid_rejected_without_attaching_or_closing_owner(self):
        writer = Writer(os.getuid() + 1)
        await self.server._client(Reader(), writer)
        self.assertFalse(self.server.accepted)
        self.assertFalse(self.owner.closed)
        self.assertTrue(writer.closed)

    async def test_discovery_client_death_aborts_owner(self):
        writer = Writer(os.getuid())
        await self.server._client(Reader(), writer)
        self.assertTrue(self.server.accepted)
        self.assertTrue(self.owner.closed)

    async def test_second_consumer_cannot_replace_first(self):
        self.server.accepted = True
        writer = Writer(os.getuid())
        await self.server._client(Reader(), writer)
        self.assertFalse(self.owner.closed)
        self.assertTrue(writer.closed)
