import asyncio
from pathlib import Path
import tempfile
import unittest
from capture import Capture, Limits, canonical
from measurement import Journal, replay
from shared_owner import Owner
from shared_session import run
from shared_rehearsal import SyntheticWire

from shared_rehearsal import exercise


class SharedSessionTests(unittest.TestCase):
    def test_last_allowed_creation_cannot_start_a_paid_watch(self):
        with tempfile.TemporaryDirectory(prefix="r1-last-frame-") as t:
            directory = Path(t)
            async def scenario():
                wire = SyntheticWire(False)
                async def factory(): return wire
                owner = Owner(factory)
                try:
                    await owner.start()
                    lease = owner.attach(5)
                    def worker():
                        with Journal(directory / 'journal') as journal:
                            with Capture(directory / 'capture', Limits(messages=1, sample_modulus=1)) as capture:
                                return asyncio.run(run(capture, lease, journal))
                    task = asyncio.create_task(asyncio.to_thread(worker))
                    await wire.incoming.put(canonical({'txType':'create','mint':'1'*31+'2','signature':'2'*88}).encode())
                    result = await asyncio.wait_for(task, 3)
                    self.assertEqual(result['outcome'], 'capture-stopped')
                    self.assertEqual(len(wire.sent), 2)
                    self.assertFalse(owner.closed)
                finally:
                    await owner.close()
            asyncio.run(scenario())
            measured = replay(directory / 'capture', directory / 'journal')
            self.assertEqual(measured['selected_without_completed_subscription_send'], 1)
            self.assertEqual(measured['local_sends_completed'], 0)

    def test_actual_capture_and_node_discovery_continue_after_normal_stop(self):
        with tempfile.TemporaryDirectory(prefix="r1-combined-") as t:
            r = asyncio.run(exercise(Path(t) / "normal", transport="pipe"))
            self.assertEqual(r["node"]["creations"], 2)
            self.assertTrue(r["discovery_after_research_stop_verified"])
            self.assertTrue(r["complete_session_replayed"])
            self.assertEqual(r["measurement"]["send_intents"], 1)
            self.assertEqual(r["research"]["upstream_connections_opened_by_research"], 0)

    def test_cleanup_failure_is_replayed_as_failure_and_node_reports_gap(self):
        with tempfile.TemporaryDirectory(prefix="r1-combined-") as t:
            r = asyncio.run(exercise(Path(t) / "failure", transport="pipe", fail_cleanup=True))
            self.assertEqual(r["measurement"]["session_outcome"], "transport-cleanup-failed")
            self.assertFalse(r["owner"]["cleanup"]["discovery_continues"])
            self.assertEqual(r["node"]["discovery_gaps"], 1)
            self.assertTrue(r["complete_session_replayed"])
