"""Private, one-consumer Unix discovery transport; no live-launch CLI."""
import asyncio
import os
import socket
import struct

from capture import CaptureError, lock, private_directory
from handoff import path_without_links


async def deliver(owner, writer, progress):
    try:
        while True:
            raw = await owner.discovery.recv()
            writer.write(raw)
            await asyncio.wait_for(writer.drain(), 0.5)
            progress["frames_sent"] += 1
    except asyncio.CancelledError:
        raise
    except Exception:
        owner.abort("discovery-output-failed")


class Server:
    def __init__(self, owner, directory):
        self.owner = owner
        self.directory = path_without_links(directory)
        self.path = self.directory / "discovery.sock"
        self.server = self.lock_fd = self.inode = None
        self.accepted = False
        self.client_tasks = set()
        self.progress = {"frames_sent": 0}
        self.connected = asyncio.Event()

    async def start(self):
        if self.server is not None or len(os.fsencode(self.path)) > 100:
            raise CaptureError("shared-endpoint")
        private_directory(self.directory)
        if self.path.exists() or self.path.is_symlink():
            raise CaptureError("shared-endpoint-exists")
        self.lock_fd = lock(self.directory)
        try:
            # Bind before listen; never expose a socket with permissive mode.
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.bind(str(self.path))
                self.inode = self.path.lstat().st_ino
                os.chmod(self.path, 0o600)
                sock.listen(1)
                sock.setblocking(False)
                self.server = await asyncio.start_unix_server(self._client, sock=sock, backlog=1)
            except BaseException:
                sock.close()
                raise
        except BaseException:
            await self.close()
            raise CaptureError("shared-endpoint-start-failed") from None

    async def _client(self, reader, writer):
        task = asyncio.current_task()
        self.client_tasks.add(task)
        owned = False
        tasks = []
        try:
            peer = writer.get_extra_info("socket")
            _, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if self.accepted or uid != os.getuid():
                return
            self.accepted = owned = True
            self.connected.set()
            tasks = [asyncio.create_task(deliver(self.owner, writer, self.progress)),
                     asyncio.create_task(reader.read(1))]
            # This is a one-way protocol. EOF or any client input ends ownership.
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except Exception:
            pass
        finally:
            if owned:
                self.owner.abort("discovery-client-ended")
            for child in tasks:
                child.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 0.5)
            except Exception:
                pass
            self.client_tasks.discard(task)

    async def close(self):
        if self.server is not None:
            self.server.close()
        for task in list(self.client_tasks):
            task.cancel()
        await asyncio.gather(*self.client_tasks, return_exceptions=True)
        if self.server is not None:
            await asyncio.wait_for(self.server.wait_closed(), 1)
        try:
            if self.inode is not None and (self.path.exists() or self.path.is_symlink()):
                if self.path.lstat().st_ino != self.inode or self.path.is_symlink():
                    raise CaptureError("shared-endpoint-replaced")
                self.path.unlink()
        finally:
            if self.lock_fd is not None:
                os.close(self.lock_fd)
                self.lock_fd = None
