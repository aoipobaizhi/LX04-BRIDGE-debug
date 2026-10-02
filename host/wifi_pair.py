"""LX04 局域网（WiFi）配对：UDP 发现 + 配对码握手 + TCP 鉴权。

USB 模式靠 `adb forward tcp:17890..17892` 把手机端口映射到 127.0.0.1；
WiFi 模式直接把这三条 TCP 连到音箱的局域网 IP，因此需要一个"怎么找到音箱、
怎么确认是本人配对"的过程，就是本模块负责的部分。

线格式：UDP 17893 上收发 UTF-8 JSON 报文，一律带 "magic": "LXB1"。

| 方向 | 报文 | 说明 |
|------|------|------|
| 电脑→音箱 | `{"cmd":"discover","magic":"LXB1","nonce":"…"}` | 广播/单播探测 |
| 音箱→电脑 | `{"cmd":"offer",…}` | 设备信息，**不含配对码** |
| 电脑→音箱 | `{"cmd":"pair","code":"123456","name":"PC"}` | 提交屏幕上显示的配对码 |
| 音箱→电脑 | `{"cmd":"pair_ok","token":"…"}` | 成功，记下 token 下次免码 |
| 音箱→电脑 | `{"cmd":"pair_deny","reason":"bad_code","left":3}` | 失败 |

配对码只显示在音箱屏幕上、只由人输入，不随广播外发，避免同网段任意主机
直接读到。配对得到的 token 由电脑保存，后续连接走 TCP 上的
`{"cmd":"wifi_auth","token":"…"}`（见 `protocol.py` 的 CONTROL 帧）。
"""
from __future__ import annotations

import json
import secrets
import socket
import time
from dataclasses import dataclass, field

MAGIC = "LXB1"
DISCOVERY_PORT = 17893
DEFAULT_TIMEOUT = 1.6
PAIR_TIMEOUT = 4.0
MAX_DATAGRAM = 4096


@dataclass
class Device:
    """一台在局域网上应答的音箱。"""

    ip: str
    name: str = "LX04"
    model: str = ""
    android: str = ""
    port: int = 17890
    video_port: int = 17891
    toast_port: int = 17892
    pairing: bool = False
    extra: dict = field(default_factory=dict)

    @staticmethod
    def from_offer(data: dict, ip: str) -> "Device":
        def _port(key: str, fallback: int) -> int:
            try:
                value = int(data.get(key, fallback))
            except (TypeError, ValueError):
                return fallback
            return value if 0 < value < 65536 else fallback

        return Device(
            ip=ip,
            name=str(data.get("device") or data.get("name") or "LX04"),
            model=str(data.get("model") or ""),
            android=str(data.get("android") or ""),
            port=_port("port", 17890),
            video_port=_port("videoPort", 17891),
            toast_port=_port("toastPort", 17892),
            pairing=bool(data.get("pairing", False)),
            extra=data,
        )

    def label(self) -> str:
        tail = " · ".join(part for part in (self.model, self.android) if part)
        state = "可配对" if self.pairing else "已关闭配对"
        return f"{self.name} {self.ip} ({state})" + (f" · {tail}" if tail else "")


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _parse(data: bytes) -> dict | None:
    try:
        obj = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict) or obj.get("magic") != MAGIC:
        return None
    return obj


def local_ipv4s() -> list[str]:
    """本机可用于局域网通信的 IPv4 地址（排除回环）。"""
    found: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    # 不产生实际流量的路由查询，用来补上 hostname 解析不到的网卡地址。
    for probe in ("8.8.8.8", "192.168.1.1"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((probe, 9))
            found.add(sock.getsockname()[0])
        except OSError:
            pass
        finally:
            sock.close()
    return sorted(ip for ip in found if not ip.startswith("127."))


def broadcast_targets() -> list[str]:
    """广播地址列表：全局广播 + 各本机地址按 /24 推出的子网广播。

    家用路由器常按 AP 隔离丢掉 255.255.255.255，所以两个都发；真正的兜底是
    用户在界面上手填 IP（`probe_ip`）。
    """
    targets = ["255.255.255.255"]
    for ip in local_ipv4s():
        parts = ip.split(".")
        if len(parts) == 4:
            targets.append(".".join(parts[:3] + ["255"]))
    seen: list[str] = []
    for item in targets:
        if item not in seen:
            seen.append(item)
    return seen


def _probe(nonce: str) -> bytes:
    return _json_bytes({"cmd": "discover", "magic": MAGIC, "nonce": nonce, "ver": 1})


def discover(
    timeout: float = DEFAULT_TIMEOUT,
    extra_ips: list[str] | None = None,
    targets: list[str] | None = None,
) -> list[Device]:
    """广播探测局域网里的 LX04，返回去重后的设备列表。

    `extra_ips` 为上次配对记住的 IP：单播给它一份探测，这样即使路由器拦广播
    也能认出老设备。
    """
    nonce = secrets.token_hex(8)
    payload = _probe(nonce)
    hops = list(targets) if targets is not None else broadcast_targets()
    for ip in extra_ips or []:
        if ip and ip not in hops:
            hops.append(ip)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    devices: dict[str, Device] = {}
    try:
        sock.bind(("", 0))
        sock.settimeout(0.15)
        for host in hops:
            try:
                sock.sendto(payload, (host, DISCOVERY_PORT))
            except OSError:
                continue
        deadline = time.monotonic() + max(0.2, timeout)
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(MAX_DATAGRAM)
            except socket.timeout:
                continue
            except OSError:
                break
            obj = _parse(data)
            if not obj or obj.get("cmd") != "offer" or obj.get("nonce") != nonce:
                continue
            devices[addr[0]] = Device.from_offer(obj, addr[0])
    finally:
        sock.close()
    return [devices[ip] for ip in sorted(devices)]


def probe_ip(ip: str, timeout: float = 1.2) -> Device | None:
    """单播探测单个 IP；用于广播被网关拦截时的手填地址。"""
    if not ip:
        return None
    found = discover(timeout=timeout, targets=[ip], extra_ips=[ip])
    return found[0] if found else None


def pair(ip: str, code: str, pc_name: str = "", timeout: float = PAIR_TIMEOUT) -> tuple[bool, str, str]:
    """向 `ip` 提交配对码，返回 (成功, token, 说明)。"""
    code = (code or "").strip()
    if not code:
        return False, "", "请先输入音箱屏幕上显示的配对码"
    if not ip:
        return False, "", "请先填写或扫描音箱 IP"

    nonce = secrets.token_hex(8)
    request = _json_bytes(
        {"cmd": "pair", "magic": MAGIC, "nonce": nonce, "code": code, "name": pc_name or ""}
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", 0))
        sock.settimeout(timeout)
        sock.sendto(request, (ip, DISCOVERY_PORT))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(MAX_DATAGRAM)
            except socket.timeout:
                break
            except OSError:
                break
            obj = _parse(data)
            if not obj or obj.get("nonce") != nonce or addr[0] != ip:
                continue
            cmd = obj.get("cmd")
            if cmd == "pair_ok":
                token = str(obj.get("token") or "")
                if not token:
                    return False, "", "音箱未返回配对令牌"
                return True, token, "配对成功"
            if cmd == "pair_deny":
                reason = str(obj.get("reason") or "bad_code")
                if reason == "bad_code":
                    left = obj.get("left")
                    tail = f"，还可试 {left} 次" if isinstance(left, int) else ""
                    return False, "", "配对码不正确" + tail
                if reason == "cooldown":
                    return False, "", "尝试次数过多，请在音箱上重新开启配对模式"
                if reason == "off":
                    return False, "", "音箱未开启 WiFi 配对模式"
                return False, "", f"配对被拒绝（{reason}）"
    except OSError as exc:
        return False, "", f"配对请求发送失败：{exc}"
    finally:
        sock.close()
    return False, "", "音箱没有响应，请确认与电脑在同一局域网，且已开启配对模式"


def auth_payload(token: str = "", code: str = "", pc_name: str = "") -> dict:
    """TCP 首帧鉴权用的 CONTROL 报文（配合 protocol.encode_json 使用）。"""
    payload = {"cmd": "wifi_auth", "name": pc_name or ""}
    if token:
        payload["token"] = token
    if code:
        payload["code"] = code
    return payload


def _main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "discover":
        found = discover()
        if not found:
            print("没有发现设备（可先用 `pair <ip> <code>` 直接指定 IP）")
            return 1
        for dev in found:
            print(dev.label())
        return 0
    if len(argv) >= 4 and argv[1] == "pair":
        ok, token, message = pair(argv[2], argv[3], socket.gethostname())
        print(message)
        if ok:
            print("token=" + token)
            return 0
        return 1
    print("用法: python wifi_pair.py discover | python wifi_pair.py pair <ip> <配对码>")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv))
