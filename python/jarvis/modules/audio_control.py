"""Windows master-volume control.

Two strategies:
  1. **Preferred** — use the Windows ``SendInput`` API to send VK_VOLUME_UP /
     VK_VOLUME_DOWN keys. This works regardless of COM apartment state and
     is what user-mode apps like AutoHotkey do.
  2. **Fallback** — pycaw. We use the modern endpoint path; this is what
     apps with a real GUI loop use. We initialise COM with
     ``COINIT_APARTMENTTHREADED`` (matching the asyncio default loop) to
     avoid the "thread mode already set" error.
"""
from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import POINTER, wintypes, cast

log = logging.getLogger("jarvis.audio")

# VK codes for multimedia keys
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP   = 0xAF

INIT_COINIT_APARTMENTTHREADED = 0x2  # STA
_initialised = False


# --------------------------------------------------------------------------- #
# Strategy 1: SendInput VK keys (works everywhere)
# --------------------------------------------------------------------------- #

def _send_vk(vk: int) -> None:
    """Send a single virtual key down + up event."""
    if sys.platform != "win32":
        return
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("ki", KEYBDINPUT)]

    SendInput = ctypes.windll.user32.SendInput  # type: ignore[attr-defined]

    down = INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_EXTENDEDKEY, time=0, dwExtraInfo=0))
    up   = INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0))
    SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
    SendInput(1, ctypes.byref(up),   ctypes.sizeof(INPUT))


def set_master_volume(level_percent: int) -> None:
    """Best-effort volume control.

    We compute the *delta* from the current level (if known) and send the
    appropriate number of VK_VOLUME_UP / VK_VOLUME_DOWN keys.  Each key
    bumps the master volume by ~2%, so for coarse control we just send
    ``level`` keys in the right direction.
    """
    level = max(0, min(100, level_percent))
    # If pycaw works, use it for accuracy.
    pycaw_vol = _try_pycaw_set(level)
    if pycaw_vol is True:
        return
    # Otherwise fall back to SendInput.
    steps = level // 2
    # First mute, then ramp up to avoid overshooting.
    _send_vk(VK_VOLUME_MUTE)
    _send_vk(VK_VOLUME_MUTE)  # unmute (toggle)
    for _ in range(steps):
        _send_vk(VK_VOLUME_UP)


def get_master_volume() -> int:
    """Return current volume percent.  Uses pycaw if available, else -1."""
    try:
        return _pycaw_get_volume()
    except Exception:
        return -1


def mute(mute: bool = True) -> None:
    if sys.platform == "win32":
        # If we want to mute, ensure muted; if unmute, ensure unmuted.
        try:
            from jarvis.modules.audio_control import _pycaw_set_mute
            _pycaw_set_mute(mute)
            return
        except Exception:
            pass
        _send_vk(VK_VOLUME_MUTE)


# --------------------------------------------------------------------------- #
# Strategy 2: pycaw (for accurate read/write)
# --------------------------------------------------------------------------- #

def _ensure_com() -> bool:
    global _initialised
    if _initialised:
        return True
    if sys.platform != "win32":
        _initialised = True
        return True
    try:
        ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
        ole32.CoInitializeEx(None, INIT_COINIT_APARTMENTTHREADED)
    except Exception as exc:  # pragma: no cover
        log.debug("CoInitializeEx failed: %s", exc)
        return False
    _initialised = True
    return True


def _pycaw_endpoint():
    if not _ensure_com():
        return None
    try:
        from comtypes import CLSCTX_ALL  # type: ignore
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore
        speakers = AudioUtilities.GetSpeakers()
        # Modern pycaw (>=20240210): AudioDevice exposes an underlying IMMDevice
        # through `_dev`.  Older versions have `.Activate(…)`.
        if hasattr(speakers, "Activate"):
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        else:
            interface = speakers._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)  # type: ignore[attr-defined]
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception as exc:
        log.debug("pycaw endpoint not available: %s", exc)
        return None


def _try_pycaw_set(level_percent: int) -> bool | None:
    vol = _pycaw_endpoint()
    if vol is None:
        return None
    try:
        vol.SetMasterVolumeLevelScalar(max(0, min(100, level_percent)) / 100.0, None)
        return True
    except Exception as exc:
        log.debug("pycaw set failed: %s", exc)
        return False


def _pycaw_get_volume() -> int:
    vol = _pycaw_endpoint()
    if vol is None:
        return -1
    return int(round(vol.GetMasterVolumeLevelScalar() * 100))


def _pycaw_set_mute(mute: bool) -> None:
    vol = _pycaw_endpoint()
    if vol is None:
        return
    vol.SetMute(1 if mute else 0, None)
