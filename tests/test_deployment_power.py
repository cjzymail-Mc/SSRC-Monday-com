"""Sleep inhibition must follow the server lifetime without touching user input."""

import io
import sys
import unittest
from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import flowboard_deploy as deploy


CONTINUOUS = 0x80000000
SYSTEM_REQUIRED = 0x00000001
DISPLAY_REQUIRED = 0x00000002


class KeepAwakeTests(unittest.TestCase):
    def test_restore_previous_requirements_on_normal_exit_and_interrupt(self):
        previous = CONTINUOUS | DISPLAY_REQUIRED
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted), patch.object(sys, "platform", "win32"), \
                    patch.object(deploy, "_set_thread_execution_state", return_value=previous) as setter, \
                    redirect_stdout(io.StringIO()) as output:
                try:
                    with deploy.keep_system_awake():
                        setter.assert_called_once_with(CONTINUOUS | SYSTEM_REQUIRED)
                        if interrupted:
                            raise KeyboardInterrupt
                except KeyboardInterrupt:
                    self.assertTrue(interrupted)
                self.assertEqual(setter.call_args_list,
                                 [call(CONTINUOUS | SYSTEM_REQUIRED), call(previous)])
                self.assertIn("Automatic sleep prevention enabled", output.getvalue())

    def test_failed_request_warns_and_does_not_claim_success_or_attempt_release(self):
        for result in (0, OSError("Unavailable"), AttributeError("Missing API")):
            with self.subTest(result=result), patch.object(sys, "platform", "win32"), \
                    patch.object(deploy, "_set_thread_execution_state", side_effect=[result]) as setter, \
                    redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as errors:
                with deploy.keep_system_awake():
                    pass
                setter.assert_called_once_with(CONTINUOUS | SYSTEM_REQUIRED)
                self.assertNotIn("[OK]", output.getvalue())
                self.assertIn("[WARNING] Could not prevent automatic sleep", errors.getvalue())

    def test_release_failure_does_not_mask_server_error(self):
        for result in (0, OSError("Unavailable")):
            with self.subTest(result=result), patch.object(sys, "platform", "win32"), \
                    patch.object(deploy, "_set_thread_execution_state", side_effect=[CONTINUOUS, result]), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                with self.assertRaisesRegex(RuntimeError, "server failure"):
                    with deploy.keep_system_awake():
                        raise RuntimeError("server failure")
                self.assertIn("Could not release sleep prevention", errors.getvalue())

    def test_non_windows_does_not_call_windows_api(self):
        with patch.object(sys, "platform", "linux"), \
                patch.object(deploy, "_set_thread_execution_state") as setter:
            with deploy.keep_system_awake():
                pass
            setter.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "Windows execution-state API")
    def test_real_windows_thread_state_is_held_and_restored(self):
        original = deploy._set_thread_execution_state(CONTINUOUS)
        self.assertNotEqual(original, 0)
        try:
            with redirect_stdout(io.StringIO()):
                with deploy.keep_system_awake():
                    held = deploy._set_thread_execution_state(CONTINUOUS | SYSTEM_REQUIRED)
                    self.assertEqual(held, CONTINUOUS | SYSTEM_REQUIRED)
            restored = deploy._set_thread_execution_state(CONTINUOUS)
            self.assertEqual(restored, CONTINUOUS)
        finally:
            deploy._set_thread_execution_state(original | CONTINUOUS)


class StartupPowerTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        # No real paths are accessed: service behavior and the native request are controlled here.
        self.settings = SimpleNamespace(config=None, db="unused.db", port=8082, lock="unused.lock",
                                        host="127.0.0.1", app=Path(__file__).resolve().parents[1],
                                        attachments=Mock(), backups=Mock(), environment=Mock(return_value={}))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(sys, "platform", "win32"))
        self.stack.enter_context(patch.object(deploy, "check_database", return_value={"schema_version": deploy.SCHEMA_VERSION}))
        self.stack.enter_context(patch.object(deploy, "host_lock", return_value=nullcontext()))
        self.stopped = self.stack.enter_context(patch.object(deploy, "assert_stopped"))
        self.setter = self.stack.enter_context(patch.object(deploy, "_set_thread_execution_state", return_value=CONTINUOUS))
        self.desktop = self.stack.enter_context(patch.object(deploy, "desktop_activity"))
        self.popen = self.stack.enter_context(patch.object(deploy.subprocess, "Popen"))
        self.process = self.popen.return_value
        self.process.poll.return_value = None
        opener = self.stack.enter_context(patch.object(deploy.urllib.request, "build_opener"))
        opener.return_value.open.return_value.__enter__.return_value = io.StringIO(
            '{"status":"ok","schema_version":%d}' % deploy.SCHEMA_VERSION)

    def test_check_and_rejected_start_never_acquire_power_request(self):
        self.assertEqual(deploy.start(self.settings, check_only=True), 0)
        self.setter.assert_not_called()
        self.popen.assert_not_called()
        self.desktop.assert_not_called()
        self.stopped.side_effect = deploy.DeploymentError("Port occupied")
        with self.assertRaisesRegex(deploy.DeploymentError, "Port occupied"):
            deploy.start(self.settings)
        self.setter.assert_not_called()
        self.popen.assert_not_called()

    def test_power_request_is_active_during_server_wait_then_released(self):
        def finish(timeout=None):
            self.setter.assert_called_once_with(CONTINUOUS | SYSTEM_REQUIRED)
            self.process.poll.return_value = 7
            return 7

        self.process.wait.side_effect = finish
        self.assertEqual(deploy.start(self.settings), 7)
        self.assertEqual(self.setter.call_args_list, [call(CONTINUOUS | SYSTEM_REQUIRED), call(CONTINUOUS)])
        self.process.terminate.assert_not_called()

    def test_ctrl_c_stops_child_before_releasing_power_request(self):
        def stop(timeout=None):
            self.setter.assert_called_once_with(CONTINUOUS | SYSTEM_REQUIRED)
            if timeout == 50:
                raise KeyboardInterrupt
            self.process.terminate.assert_called_once()
            self.process.poll.return_value = 0
            return 0

        self.process.wait.side_effect = stop
        self.assertEqual(deploy.start(self.settings), 0)
        self.assertEqual(self.setter.call_args_list, [call(CONTINUOUS | SYSTEM_REQUIRED), call(CONTINUOUS)])

    def test_spawn_failure_releases_power_request(self):
        self.popen.side_effect = OSError("Cannot start process")
        with self.assertRaisesRegex(OSError, "Cannot start process"):
            deploy.start(self.settings)
        self.assertEqual(self.setter.call_args_list, [call(CONTINUOUS | SYSTEM_REQUIRED), call(CONTINUOUS)])

    def test_unhealthy_child_releases_power_request(self):
        self.process.poll.return_value = 3
        with self.assertRaisesRegex(deploy.DeploymentError, "did not become healthy"):
            deploy.start(self.settings)
        self.assertEqual(self.setter.call_args_list, [call(CONTINUOUS | SYSTEM_REQUIRED), call(CONTINUOUS)])

    def test_failed_power_request_still_runs_the_server(self):
        self.setter.return_value = 0
        def finish(timeout=None):
            self.process.poll.return_value = 0
            return 0

        self.process.wait.side_effect = finish
        with redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(deploy.start(self.settings), 0)
        self.popen.assert_called_once()
        self.setter.assert_called_once_with(CONTINUOUS | SYSTEM_REQUIRED)
        self.assertIn("Could not prevent automatic sleep", errors.getvalue())

    def test_desktop_activity_repeats_while_waiting_and_stops_at_exit(self):
        self.process.wait.side_effect = [deploy.subprocess.TimeoutExpired("server", 50), 0]
        self.process.poll.side_effect = [None, 0]
        self.assertEqual(deploy.start(self.settings), 0)
        self.assertEqual(self.desktop.return_value.call_count, 2)
        self.assertEqual(self.process.wait.call_args_list, [call(timeout=50), call(timeout=50)])


if __name__ == "__main__":
    unittest.main()
