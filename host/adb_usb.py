"""Find adb.exe, list USB devices, and open TCP 17890/17891/17892 over the USB cable."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
PORT = 17890
VIDEO_PORT = 17891
TOAST_PORT = 17892
# 无线 ADB（adb tcpip / adb connect）用的端口，Android 8.1 原生支持。
TCPIP_PORT = 5555
PKG = "com.lx04.pcbridge"
SERVICE = PKG + "/.BridgeService"


def _bundled_adb_paths() -> list[Path]:
    here = Path(__file__).resolve().parent
    paths = [here / "adb" / "adb.exe"]
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", "."))
        exe_dir = Path(sys.executable).resolve().parent
        paths = [
            meipass / "adb" / "adb.exe",
            exe_dir / "adb" / "adb.exe",
            exe_dir / "adb.exe",
        ] + paths
    return paths


def find_adb() -> str | None:
    env = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    candidates: list[str] = [str(path) for path in _bundled_adb_paths()]
    candidates.extend(
        [
            shutil.which("adb") or "",
            str(Path(r"D:\AndroidSDK\platform-tools\adb.exe")),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe"),
            r"C:\Android\platform-tools\adb.exe",
            r"C:\platform-tools\adb.exe",
        ]
    )
    if env:
        candidates.insert(len(_bundled_adb_paths()), str(Path(env) / "platform-tools" / "adb.exe"))
    seen: set[str] = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if Path(path).exists():
            return path
    return None


def _run(adb: str, args: list[str], timeout: float = 8.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [adb, *args],
        capture_output=True,
        # 不能只写 text=True：那样会按系统 ANSI 代码页（中文 Windows 上是 GBK）
        # 解码 adb 的输出，一旦出现非 GBK 字节，读取线程会抛 UnicodeDecodeError，
        # stdout 变成空、returncode 也可能失真，于是所有 adb 结果都不可信。
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        cwd=str(Path(adb).resolve().parent),
    )


def kill_server(adb: str) -> None:
    if not adb:
        return
    _run(adb, ["kill-server"], timeout=5)


def list_devices(adb: str) -> list[str]:
    result = _run(adb, ["devices"])
    devices: list[str] = []
    for line in (result.stdout or "").splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def wait_for_device(adb: str, serial: str | None = None, timeout: float = 25.0) -> None:
    args = ["-s", serial] if serial else []
    try:
        result = _run(adb, [*args, "wait-for-device"], timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("音箱 USB 暂时掉线，请拔掉数据线再插上。") from exc
    if result.returncode != 0:
        raise RuntimeError("音箱 USB 暂时掉线，请拔掉数据线再插上。")


def enable_usb_microphone(adb: str, serial: str | None = None) -> str:
    """Keep USB as ADB-only.

    LX04 can enumerate a USB Audio gadget named "LX04 Microphone", but Windows
    usbaudio.sys fails to start (code 10 / protocol error). Switching the gadget
    also drops ADB. Do not change persist.sys.usb.config away from adb.
    """
    args = ["-s", serial] if serial else []
    script = (
        "setprop persist.sys.usb.config adb; "
        "getprop persist.sys.usb.config; echo; getprop sys.usb.config; echo; "
        "ls -l /config/usb_gadget/g1/configs/b.1/"
    )
    result = _run(adb, [*args, "shell", script], timeout=8)
    return ((result.stdout or "") + "\n" + (result.stderr or "")).strip()


def usb_mic_links_ok(status_text: str) -> bool:
    return "audio_source" in status_text.replace("\n", " ")


def restore_adb_only(adb: str, serial: str | None = None) -> None:
    args = ["-s", serial] if serial else []
    script = (
        "setprop persist.sys.usb.config adb; "
        "setprop sys.usb.config adb; "
        "(stop adbd; sleep 1; start adbd) >/dev/null 2>&1 &"
    )
    _run(adb, [*args, "shell", script], timeout=6)


def take_speaker_mic(adb: str, serial: str | None = None) -> str:
    """Stop XiaoAi always-on VPM so tinycap can use the dual digital mics."""
    args = ["-s", serial] if serial else []
    last = ""
    text = ""
    for _ in range(8):
        result = _run(adb, [*args, "shell", "stop mivpm; getprop init.svc.mivpm"], timeout=8)
        text = ((result.stdout or "") + " " + (result.stderr or "")).strip()
        status = (result.stdout or "").strip().splitlines()
        last = status[-1].strip() if status else ""
        if last == "stopped":
            return "已暂停小爱唤醒麦，音箱麦克风交给桥接"
        time.sleep(0.15)
    return "小爱唤醒麦未能释放（mivpm=" + (last or text or "unknown") + "）"


def release_speaker_mic(adb: str, serial: str | None = None) -> str:
    args = ["-s", serial] if serial else []
    result = _run(adb, [*args, "shell", "start mivpm; getprop init.svc.mivpm"], timeout=8)
    text = ((result.stdout or "") + " " + (result.stderr or "")).strip()
    status = (result.stdout or "").strip().splitlines()
    last = status[-1].strip() if status else ""
    if last not in {"running", "restarting"}:
        return "小爱唤醒麦未恢复（mivpm=" + (last or text or "unknown") + "）"
    return "已恢复小爱唤醒麦"


def enable_tcpip(adb: str, serial: str | None = None, port: int = TCPIP_PORT) -> str:
    """让音箱上的 adbd 监听 TCP 端口，之后可以拔线走 WiFi。

    Android 8.1 没有"无线调试配对"（那是 Android 11 才有的），但 `adb tcpip`
    从很早就支持：它把 adbd 重启到 TCP 模式，仍然用现有的 adb 密钥鉴权。
    需要设备此刻通过 USB 连着。
    """
    args = ["-s", serial] if serial else []
    result = _run(adb, [*args, "tcpip", str(port)], timeout=15)
    text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    if result.returncode != 0 or "error" in text.lower():
        raise RuntimeError(text or f"adb tcpip {port} 失败")
    return text or f"adbd 已在 {port} 端口监听，可以拔线了"


def connect_wifi(adb: str, host: str, port: int = TCPIP_PORT, timeout: float = 15.0) -> str:
    """adb connect 到音箱的局域网地址；失败抛异常。"""
    if not host:
        raise RuntimeError("请先填写音箱的局域网 IP")
    target = f"{host}:{port}"
    result = _run(adb, ["connect", target], timeout=timeout)
    text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    low = text.lower()
    bad = ("cannot connect" in low or "unable to connect" in low
           or "failed to connect" in low or "refused" in low)
    if result.returncode != 0 or bad:
        raise RuntimeError(text or f"连不上 {target}；请在音箱上先用数据线执行过一次 adb tcpip")
    return text or f"已连接 {target}"


def disconnect_wifi(adb: str, host: str, port: int = TCPIP_PORT) -> None:
    if not adb or not host:
        return
    _run(adb, ["disconnect", f"{host}:{port}"], timeout=6)


def wifi_serial(host: str, port: int = TCPIP_PORT) -> str:
    """走 WiFi 时 adb 的 -s 参数值。"""
    return f"{host}:{port}"


def device_ip(adb: str, serial: str | None = None) -> str:
    """读音箱的局域网 IPv4，用来替用户填好 IP（优先 wlan0）。"""
    args = ["-s", serial] if serial else []
    for script in ("ip -f inet addr show wlan0", "ip route", "getprop dhcp.wlan0.ipaddress"):
        try:
            result = _run(adb, [*args, "shell", script], timeout=8)
        except Exception:
            continue
        text = (result.stdout or "") + "\n" + (result.stderr or "")
        for token in text.replace("/", " ").replace(":", " ").split():
            parts = token.split(".")
            if len(parts) != 4:
                continue
            if all(part.isdigit() and 0 <= int(part) < 256 for part in parts):
                if not token.startswith("127.") and not token.startswith("0."):
                    return token
    return ""


def usb_forward(adb: str, serial: str | None = None) -> None:
    args = ["-s", serial] if serial else []
    last_err = ""
    for port in (PORT, VIDEO_PORT, TOAST_PORT):
        _run(adb, [*args, "forward", "--remove", f"tcp:{port}"])
        result = _run(adb, [*args, "forward", f"tcp:{port}", f"tcp:{port}"])
        if result.returncode != 0:
            last_err = (result.stderr or result.stdout or f"adb forward {port} failed").strip()
            raise RuntimeError(last_err)


def install_apk(adb: str, apk: Path, serial: str | None = None) -> str:
    args = ["-s", serial] if serial else []
    result = _run(adb, [*args, "install", "-r", "-t", str(apk)], timeout=120)
    text = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError(text.strip() or "adb install failed")
    grant_bridge_permission(adb, serial)
    whitelist_bridge(adb, serial)
    start_bridge_service(adb, serial)
    return text.strip()


ROTATION_LABELS = ("正向", "倒转")


def clamp_rotation(value: object) -> int:
    """Only Surface.ROTATION_0 and ROTATION_180."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    n = ((n % 4) + 4) % 4
    return 2 if n >= 2 else 0


def rotation_choice(value: object) -> int:
    """0 = 正向, 1 = 倒转."""
    return 1 if clamp_rotation(value) == 2 else 0


def rotation_label(value: object) -> str:
    return ROTATION_LABELS[rotation_choice(value)]


def set_user_rotation(adb: str, rotation: int, serial: str | None = None) -> None:
    """Lock the speaker display to Surface.ROTATION_* via system settings.

    LX04 has no gyro, so accelerometer_rotation stays off. Shell can write
    Settings.System.USER_ROTATION; `wm user-rotation` is a no-op on 8.1.
    """
    rotation = clamp_rotation(rotation)
    args = ["-s", serial] if serial else []
    script = (
        "settings put system accelerometer_rotation 0; "
        f"settings put system user_rotation {rotation}; "
        f"wm user-rotation lock {rotation} >/dev/null 2>&1; "
        "true"
    )
    result = _run(adb, [*args, "shell", script], timeout=8)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "user_rotation failed").strip()
        raise RuntimeError(err)


def grant_bridge_permission(adb: str, serial: str | None = None) -> None:
    args = ["-s", serial] if serial else []
    _run(adb, [*args, "shell", "pm", "grant", PKG, "android.permission.RECORD_AUDIO"])
    _run(adb, [*args, "shell", "appops", "set", PKG, "WRITE_SETTINGS", "allow"])


def whitelist_bridge(adb: str, serial: str | None = None) -> None:
    args = ["-s", serial] if serial else []
    script = (
        f"dumpsys deviceidle whitelist +{PKG} >/dev/null 2>&1; "
        f"am set-inactive {PKG} false >/dev/null 2>&1; "
        f"cmd appops set {PKG} RUN_IN_BACKGROUND allow >/dev/null 2>&1; "
        f"cmd appops set {PKG} RUN_ANY_IN_BACKGROUND allow >/dev/null 2>&1; "
        f"cmd appops set {PKG} WRITE_SETTINGS allow >/dev/null 2>&1; "
        "true"
    )
    _run(adb, [*args, "shell", script], timeout=10)


def start_bridge_service(adb: str, serial: str | None = None) -> None:
    args = ["-s", serial] if serial else []
    result = _run(
        adb,
        [*args, "shell", "am", "start-foreground-service", "-n", SERVICE],
        timeout=10,
    )
    if result.returncode != 0:
        _run(adb, [*args, "shell", "am", "startservice", "-n", SERVICE], timeout=10)


def start_bridge_ui(adb: str, serial: str | None = None) -> None:
    args = ["-s", serial] if serial else []
    _run(adb, [*args, "shell", "am", "start", "-n", f"{PKG}/.MainActivity"], timeout=8)


def hide_bridge_ui(adb: str, serial: str | None = None) -> None:
    args = ["-s", serial] if serial else []
    _run(adb, [*args, "shell", "input", "keyevent", "KEYCODE_HOME"], timeout=8)


def bridge_pid(adb: str, serial: str | None = None) -> str:
    args = ["-s", serial] if serial else []
    result = _run(adb, [*args, "shell", "pidof", PKG])
    return (result.stdout or "").strip().split()[0] if (result.stdout or "").strip() else ""


def ensure_bridge_running(adb: str, serial: str | None = None) -> str:
    grant_bridge_permission(adb, serial)
    whitelist_bridge(adb, serial)
    start_bridge_service(adb, serial)
    time.sleep(0.5)
    pid = bridge_pid(adb, serial)
    if pid:
        return "后台服务已运行 pid=" + pid
    start_bridge_service(adb, serial)
    time.sleep(0.7)
    pid = bridge_pid(adb, serial)
    if pid:
        return "后台服务已拉起 pid=" + pid
    args = ["-s", serial] if serial else []
    err = _run(adb, [*args, "shell", "am", "start-foreground-service", "-n", SERVICE], timeout=10)
    detail = ((err.stderr or "") + " " + (err.stdout or "")).strip()
    raise RuntimeError("无法在音箱上拉起后台服务（未打开窗口）。" + (detail or "请确认已安装 APK。"))
