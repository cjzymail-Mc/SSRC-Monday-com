import ctypes
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

from flowboard import desktop_activity as activity


class DesktopActivityTests(unittest.TestCase):
    def make_activity(self):
        user = Mock()
        user.GetAsyncKeyState.return_value = 0
        user.SystemParametersInfoW.return_value = 1
        user.SendInput.return_value = 4
        with patch.object(ctypes, "WinDLL", return_value=user, create=True):
            instance = activity.DesktopActivity()
        return instance, user

    def test_two_complete_numlock_presses_are_one_serial_batch(self):
        instance, user = self.make_activity()
        captured = []

        def send(count, events, size):
            captured.extend((event.type, event.value.ki.wVk, event.value.ki.wScan, event.value.ki.dwFlags)
                            for event in events)
            self.assertEqual(size, ctypes.sizeof(activity.INPUT))
            return count

        user.SendInput.side_effect = send
        self.assertTrue(instance._pulse())
        self.assertEqual(captured, [(1, 0x90, 0x45, flag) for flag in (1, 3, 1, 3)])
        user.SendInput.assert_called_once()

    def test_pressed_modifiers_and_numlock_skip_input(self):
        for held in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0x90):
            with self.subTest(key=held):
                instance, user = self.make_activity()
                user.GetAsyncKeyState.side_effect = lambda key: 0x8000 if key == held else 0
                self.assertFalse(instance._pulse())
                user.SendInput.assert_not_called()

    def test_partial_batch_completes_only_remaining_events_once(self):
        for sent in (1, 2, 3):
            with self.subTest(sent=sent):
                instance, user = self.make_activity()
                user.SendInput.side_effect = [sent, 4 - sent]
                self.assertTrue(instance._pulse())
                remaining = user.SendInput.call_args.args
                self.assertEqual(remaining[0], 4 - sent)
                self.assertEqual([remaining[1][i].value.ki.dwFlags for i in range(4 - sent)], [1, 3, 1, 3][sent:])
                self.assertEqual(user.SendInput.call_count, 2)

    def test_failed_input_warns_once_then_reports_recovery(self):
        instance, user = self.make_activity()
        user.SendInput.side_effect = [0, 0, 4]
        with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as errors:
            instance.refresh()
            instance.refresh()
            self.assertNotIn("[OK]", output.getvalue())
            instance.refresh()
        self.assertEqual(errors.getvalue().count("[WARNING]"), 1)
        self.assertIn("Automatic lock prevention active", output.getvalue())

    def test_failed_partial_batch_warns_about_numlock_state(self):
        instance, user = self.make_activity()
        user.SendInput.side_effect = [1, 0]
        with redirect_stderr(io.StringIO()) as errors:
            instance.refresh()
        self.assertIn("Num Lock state may have changed", errors.getvalue())
        self.assertEqual(user.SendInput.call_count, 2)

    def test_screen_saver_policy_failure_is_visible_and_does_not_inject(self):
        instance, user = self.make_activity()

        def blocked(action, param, value, flags):
            self.assertEqual(action, 0x1026)
            ctypes.cast(value, ctypes.POINTER(activity.wintypes.BOOL)).contents.value = 1
            return 1

        user.SystemParametersInfoW.side_effect = blocked
        with patch.object(sys, "platform", "win32"), \
                patch.object(ctypes, "WinDLL", return_value=user, create=True), \
                redirect_stderr(io.StringIO()) as errors:
            refresh = activity.desktop_activity()
            refresh()
        self.assertIn("blocks simulated input", errors.getvalue())
        user.SendInput.assert_not_called()

    def test_non_windows_does_not_load_user32(self):
        with patch.object(sys, "platform", "linux"), patch.object(activity, "DesktopActivity") as factory:
            activity.desktop_activity()()
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
