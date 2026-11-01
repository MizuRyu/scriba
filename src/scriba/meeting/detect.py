"""会議アプリがマイクを使っているか（通話中か）を CoreAudio のプロセス情報から読む。

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
_UTF8 = 0x08000100


class _Address(ctypes.Structure):
    _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("element", ctypes.c_uint32)]


_ca = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreAudio"))
_cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
_cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
_cf.CFRelease.argtypes = [ctypes.c_void_p]


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
