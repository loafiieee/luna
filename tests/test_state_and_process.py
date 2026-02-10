import os
import tempfile
import time
import unittest
from pathlib import Path

from backend.utils.state import ServersState
from backend.utils.process_manager import ServerProcessManager


class StateTests(unittest.TestCase):
    def test_read_write_mutate(self):
        with tempfile.TemporaryDirectory() as td:
            state = ServersState(Path(td) / "servers.json")
            self.assertEqual(state.read(), [])
            state.write([{"name": "a"}])
            self.assertEqual(state.read()[0]["name"], "a")
            state.mutate(lambda items: items + [{"name": "b"}])
            self.assertEqual(len(state.read()), 2)


class ProcessManagerTests(unittest.TestCase):
    def test_start_poll_stop(self):
        mgr = ServerProcessManager()
        sid = mgr.start(["python", "-c", "import time; print('hello'); time.sleep(0.2); print('bye')"])
        time.sleep(0.4)
        out = "\n".join(mgr.poll_output(sid))
        self.assertIn("hello", out)
        self.assertIn("bye", out)
        status = mgr.status(sid)
        self.assertFalse(status["running"])
        mgr.stop(sid)


if __name__ == "__main__":
    unittest.main()
