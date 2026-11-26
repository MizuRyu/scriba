"""アプリがマイクを使っているか（通話中か）と OS の既定の入力デバイスを CoreAudio から、入力の無い時間を CoreGraphics から、
電池で動いているかを IOKit から読む。

macOS 14.2 以降の AudioProcess オブジェクトを ctypes で引く。アプリは bundle id の接頭辞で
指定する（config.toml の meeting_apps）。Teams は通話中に modulehost が入力を開き、通話が終わると閉じる。
"""

import ctypes
import ctypes.util

def _fourcc(code: str) -> int:
    return int.from_bytes(code.encode("ascii"), "big")


_SYSTEM_OBJECT = 1
_SCOPE_GLOBAL = _fourcc("glob")
_PROCESS_LIST = _fourcc("prs#")
_BUNDLE_ID = _fourcc("pbid")
_RUNNING_INPUT = _fourcc("piri")
_DEFAULT_INPUT = _fourcc("dIn ")
_UTF8 = 0x08000100


class _Address(ctypes.Structure):
    _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("element", ctypes.c_uint32)]


_ca = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreAudio"))
_cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
_cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
_cf.CFRelease.argtypes = [ctypes.c_void_p]
_cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
_cg.CGEventSourceSecondsSinceLastEventType.restype = ctypes.c_double
_cg.CGEventSourceSecondsSinceLastEventType.argtypes = [ctypes.c_int32, ctypes.c_uint32]
_HID_SYSTEM_STATE = 1
_ANY_INPUT_EVENT = 0xFFFFFFFF
_iokit = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
_iokit.IOPSGetTimeRemainingEstimate.restype = ctypes.c_double
_TIME_REMAINING_UNLIMITED = -2.0  # 電源アダプタにつながっている。電池の無い Mac もこの値を返す


def _get(obj: int, selector: int, buf) -> bool:
    addr = _Address(selector, _SCOPE_GLOBAL, 0)
    size = ctypes.c_uint32(ctypes.sizeof(buf))
    return _ca.AudioObjectGetPropertyData(obj, ctypes.byref(addr), 0, None, ctypes.byref(size), ctypes.byref(buf)) == 0


def _process_ids() -> list[int]:
    addr = _Address(_PROCESS_LIST, _SCOPE_GLOBAL, 0)
    size = ctypes.c_uint32(0)
    if _ca.AudioObjectGetPropertyDataSize(_SYSTEM_OBJECT, ctypes.byref(addr), 0, None, ctypes.byref(size)) != 0:
        return []
    ids = (ctypes.c_uint32 * (size.value // 4))()
    if not _get(_SYSTEM_OBJECT, _PROCESS_LIST, ids):
        return []
    return list(ids)


def _bundle_id(obj: int) -> str:
    ref = ctypes.c_void_p()
    if not _get(obj, _BUNDLE_ID, ref) or not ref.value:
        return ""
    buf = ctypes.create_string_buffer(256)
    ok = _cf.CFStringGetCString(ref, buf, len(buf), _UTF8)
    _cf.CFRelease(ref)
    return buf.value.decode() if ok else ""


def mic_in_use(apps: list[str]) -> bool:
    """apps（bundle id の接頭辞）のいずれかのプロセスがマイク入力を使っていれば True。"""
    prefixes = tuple(apps)
    for obj in _process_ids():
        running = ctypes.c_uint32()
        if _bundle_id(obj).startswith(prefixes) and _get(obj, _RUNNING_INPUT, running) and running.value:
            return True
    return False


def default_input_device() -> int | None:
    """OS の既定の入力デバイスの ID。入力が無ければ None。同じデバイスでも抜き差しで ID は変わる。"""
    device = ctypes.c_uint32()
    return device.value if _get(_SYSTEM_OBJECT, _DEFAULT_INPUT, device) and device.value else None


def input_idle_seconds() -> float:
    """キーボード、マウス、トラックパッドの最後の入力からの秒数。"""
    return _cg.CGEventSourceSecondsSinceLastEventType(_HID_SYSTEM_STATE, _ANY_INPUT_EVENT)


def on_battery() -> bool:
    """電池で動いている間は True。"""
    return _iokit.IOPSGetTimeRemainingEstimate() != _TIME_REMAINING_UNLIMITED
