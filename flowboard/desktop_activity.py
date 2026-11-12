"""Keep the signed-in Windows desktop active using paired Num Lock events."""

import ctypes
import sys
from ctypes import wintypes


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUTUNION(ctypes.Union):
    # MOUSEINPUT supplies the native union's full size and alignment on both x86 and x64.
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("value", INPUTUNION)]


class DesktopActivity:
    def __init__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self.user.SendInput.restype = wintypes.UINT
        self.user.GetAsyncKeyState.argtypes = (ctypes.c_int,)
        self.user.GetAsyncKeyState.restype = wintypes.SHORT
        self.user.SystemParametersInfoW.argtypes = (wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT)
        self.user.SystemParametersInfoW.restype = wintypes.BOOL
        blocked = wintypes.BOOL()
        if not self.user.SystemParametersInfoW(0x1026, 0, ctypes.byref(blocked), 0):  # SPI_GETBLOCKSENDINPUTRESETS
            raise ctypes.WinError(ctypes.get_last_error())
        if blocked.value:
            raise OSError("Windows blocks simulated input from resetting the screen saver timer")
        self.warned = False
        self.announced = False

    def _pulse(self):
        # Avoid modifier shortcuts (including Mouse Keys) and a physically held Num Lock key.
        if any(self.user.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0x90)):
            return False
        # Send both complete key presses in one batch. User input cannot interleave between them.
        events = (INPUT * 4)()
        for event, flags in zip(events, (1, 3, 1, 3)):  # extended key; extended key + key up
            event.type = 1  # INPUT_KEYBOARD
            event.value.ki = KEYBDINPUT(0x90, 0x45, flags, 0, 0)  # VK_NUMLOCK
        sent = self.user.SendInput(4, events, ctypes.sizeof(INPUT))
        if 0 < sent < 4:
            # Complete a partial batch once so Num Lock is not left down or toggled.
            remainder = ctypes.cast(ctypes.byref(events, sent * ctypes.sizeof(INPUT)), ctypes.POINTER(INPUT))
            sent += self.user.SendInput(4 - sent, remainder, ctypes.sizeof(INPUT))
        if sent != 4:
            detail = "; Num Lock state may have changed" if sent else ""
            raise OSError(f"Windows accepted {sent}/4 Num Lock events (desktop may be locked or input blocked){detail}")
        return True

    def refresh(self):
        try:
            if not self._pulse():
                if not self.announced:
                    print("[INFO] Automatic lock prevention waiting for held modifier/Num Lock keys to be released.", flush=True)
                return
        except (OSError, AttributeError) as error:
            if not self.warned:
                print(f"[WARNING] Automatic lock prevention unavailable: {error}", file=sys.stderr, flush=True)
            self.warned = True
        else:
            if not self.announced or self.warned:
                print("[OK] Automatic lock prevention active: paired Num Lock presses every 50 seconds while Flowboard runs.",
                      flush=True)
            self.announced = True
            self.warned = False


def desktop_activity():
    """Return a refresh callback; failures must not stop the LAN server."""
    if sys.platform == "win32":
        try:
            return DesktopActivity().refresh
        except (OSError, AttributeError) as error:
            print(f"[WARNING] Automatic lock prevention unavailable: {error}", file=sys.stderr, flush=True)
    return lambda: None
