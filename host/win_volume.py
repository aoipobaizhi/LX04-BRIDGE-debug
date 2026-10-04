"""Read and set the Windows default playback volume (system volume keys)."""
from __future__ import annotations

import time

_cached_endpoint = None
_cached_device_id = ""
_last_device_check = 0.0
_enum = None
# 默认设备 id 最多这么久核对一次。核对本身约 4ms，逐次调用返回缓存只要 0.06ms，
# 而"重建接口"要 52ms（pycaw 的 GetSpeakers 每次都 CreateDevice）——所以绝不能每次调用都重建。
DEVICE_CHECK_INTERVAL = 1.5


def get_state() -> tuple[float | None, bool]:
    """Return (scalar 0..1, muted). One COM round-trip."""
    volume = _endpoint_volume()
    if volume is None:
        return None, False
    muted = False
    scalar = None
    try:
        muted = bool(int(volume.GetMute()))
    except Exception:
        pass
    try:
        scalar = max(0.0, min(1.0, float(volume.GetMasterVolumeLevelScalar())))
    except Exception:
        pass
    if scalar is not None and scalar <= 0.001:
        muted = True
    return scalar, muted


def get_scalar() -> float | None:
    scalar, _muted = get_state()
    return scalar


def is_silent() -> bool:
    _scalar, muted = get_state()
    return muted


def set_scalar(level: float) -> bool:
    volume = _endpoint_volume()
    if volume is None:
        return False
    value = max(0.0, min(1.0, float(level)))
    try:
        volume.SetMasterVolumeLevelScalar(value, None)
        return True
    except Exception:
        _clear_cached_endpoint()
        return False


def _clear_cached_endpoint() -> None:
    global _cached_endpoint, _cached_device_id, _last_device_check
    _cached_endpoint = None
    _cached_device_id = ""
    _last_device_check = 0.0


def invalidate() -> None:
    """默认播放设备切换后调用，丢弃缓存的音量接口。"""
    _clear_cached_endpoint()


def _device_id(speakers) -> str:
    try:
        return str(speakers._dev.GetId())
    except Exception:
        return ""


def _enumerator():
    """复用一个 IMMDeviceEnumerator（创建一次约 12ms，之后查询默认端点约 4ms）。"""
    global _enum
    if _enum is not None:
        return _enum
    try:
        import comtypes
        from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
        from pycaw.constants import CLSID_MMDeviceEnumerator

        _enum = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER
        )
    except Exception:
        _enum = None
    return _enum


def _default_device_id() -> str:
    enum = _enumerator()
    if enum is None:
        return ""
    try:
        from pycaw.constants import EDataFlow, ERole

        dev = enum.GetDefaultAudioEndpoint(EDataFlow.eRender.value, ERole.eMultimedia.value)
        return str(dev.GetId())
    except Exception:
        return ""


def _build_endpoint():
    """真的需要重建时才走这里（约 53ms）。返回 (endpoint, device_id)。"""
    try:
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities
    except Exception:
        return None, ""
    try:
        speakers = AudioUtilities.GetSpeakers()
    except Exception:
        return None, ""
    if speakers is None:
        return None, ""
    dev_id = _device_id(speakers)
    try:
        endpoint = speakers.EndpointVolume
    except Exception:
        endpoint = None
    if endpoint is None:
        try:
            from pycaw.api.endpointvolume import IAudioEndpointVolume

            iface = speakers._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            endpoint = iface.QueryInterface(IAudioEndpointVolume)
        except Exception:
            return None, dev_id
    return endpoint, dev_id


def _endpoint_volume():
    """按"设备 id"缓存音量接口，同时把每次调用的开销压到最低。

    历史：以前永久缓存一次 → 连接流程里"先读音量、后切默认设备"，缓存绑死在旧设备上，
    拖任务栏主音量音箱没反应。改成每次 GetSpeakers() 核对后，虽然正确了，
    但 GetSpeakers() 每次 CreateDevice ≈ 52ms，80ms 轮询时几乎吃满一个核。
    现在：复用枚举器 + 设备 id 每 1.5 秒才核对一次；没变就直接用缓存（0.06ms）。
    """
    global _cached_endpoint, _cached_device_id, _last_device_check
    now = time.monotonic()
    if _cached_endpoint is not None and now - _last_device_check < DEVICE_CHECK_INTERVAL:
        return _cached_endpoint
    _last_device_check = now
    dev_id = _default_device_id()
    if _cached_endpoint is not None and (not dev_id or dev_id == _cached_device_id):
        # 设备没变（或暂时查不到）→ 继续用缓存，不付重建代价
        return _cached_endpoint
    endpoint, built_id = _build_endpoint()
    if endpoint is None:
        return _cached_endpoint
    _cached_endpoint = endpoint
    _cached_device_id = dev_id or built_id or ""
    return endpoint
