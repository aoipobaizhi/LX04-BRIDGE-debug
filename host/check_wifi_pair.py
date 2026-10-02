#!/usr/bin/env python3
"""WiFi（局域网）配对的端到端自测。

在 127.0.0.1 上起一个"假音箱"：UDP 17893 按 WifiPairServer.java 的报文格式应答
发现与配对，TCP 上按 TcpBridgeServer 的规则要求首帧 wifi_auth 鉴权。然后用
host/wifi_pair.py 与 host/protocol.py 走一遍真实流程。

跑法：
    python check_wifi_pair.py
不依赖 PySide6，可单独运行。
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import protocol  # noqa: E402
import wifi_pair  # noqa: E402

MAGIC = "LXB1"
PIN = "135790"
TOKEN = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


class FakeSpeaker:
    """模拟音箱端：UDP 发现/配对 + TCP 首帧鉴权。"""

    def __init__(self, tcp_port: int) -> None:
        self.tcp_port = tcp_port
        self.pairing = True
        self.pin = PIN
        self.token = TOKEN
        self.attempts = 0
        self.udp_requests: list[dict] = []
        self.auth_frames: list[dict] = []
        self.status_sent = 0
        self._stop = threading.Event()
        self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._udp.bind(("127.0.0.1", wifi_pair.DISCOVERY_PORT))
        self._udp.settimeout(0.2)
        self._tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._tcp.bind(("127.0.0.1", self.tcp_port))
        self._tcp.listen(1)
        self._tcp.settimeout(0.2)
        self.auth_ok = False
        self.threads = [
            threading.Thread(target=self._udp_loop, daemon=True),
            threading.Thread(target=self._tcp_loop, daemon=True),
        ]

    def start(self) -> None:
        for thread in self.threads:
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        for thread in self.threads:
            thread.join(timeout=2.0)
        self._udp.close()
        self._tcp.close()

    # -- UDP：发现 + 配对 --------------------------------------------------
    def _udp_loop(self) -> None:
        while not self._stop.is_set():
            try:
                data, addr = self._udp.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                req = json.loads(data.decode("utf-8"))
            except ValueError:
                continue
            if req.get("magic") != MAGIC:
                continue
            self.udp_requests.append(req)
            cmd = req.get("cmd")
            if cmd == "discover":
                self._reply(addr, {
                    "cmd": "offer", "magic": MAGIC, "nonce": req.get("nonce", ""),
                    "device": "LX04", "model": "Xiaomi LX04", "android": "8.1.0",
                    "ip": "127.0.0.1", "port": self.tcp_port,
                    "videoPort": protocol.VIDEO_PORT, "toastPort": protocol.TOAST_PORT,
                    "pairing": self.pairing, "paired": bool(self.token),
                })
            elif cmd == "pair":
                if not self.pairing:
                    self._reply(addr, {"cmd": "pair_deny", "magic": MAGIC,
                                       "nonce": req.get("nonce", ""), "reason": "off"})
                elif str(req.get("code", "")) == self.pin:
                    self.pairing = False
                    self._reply(addr, {"cmd": "pair_ok", "magic": MAGIC,
                                       "nonce": req.get("nonce", ""), "token": self.token,
                                       "ip": "127.0.0.1"})
                else:
                    self.attempts += 1
                    self._reply(addr, {"cmd": "pair_deny", "magic": MAGIC,
                                       "nonce": req.get("nonce", ""),
                                       "reason": "bad_code", "left": max(0, 5 - self.attempts)})

    def _reply(self, addr, payload: dict) -> None:
        try:
            self._udp.sendto(json.dumps(payload, ensure_ascii=False).encode("utf-8"), addr)
        except OSError:
            pass

    # -- TCP：HELLO + 首帧鉴权 --------------------------------------------
    def _tcp_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._tcp.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    @staticmethod
    def _send(conn: socket.socket, msg_type: int, payload: bytes = b"", seq: int = 1) -> None:
        conn.sendall(protocol.encode(msg_type, payload, seq=seq))

    @staticmethod
    def _recv(conn: socket.socket) -> protocol.Frame | None:
        header = b""
        while len(header) < protocol.HEADER.size:
            piece = conn.recv(protocol.HEADER.size - len(header))
            if not piece:
                return None
            header += piece
        decoded = protocol.try_decode_header(header)
        if decoded is None:
            return None
        msg_type, flags, seq, ts, length = decoded
        payload = b""
        while len(payload) < length:
            piece = conn.recv(length - len(payload))
            if not piece:
                return None
            payload += piece
        return protocol.Frame(msg_type, flags, seq, ts, payload)

    def _serve(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(6.0)
            self._send(conn, protocol.HELLO, json.dumps({
                "device": "LX04", "model": "Xiaomi LX04", "android": "8.1.0",
                "sampleRate": 48000, "channels": 1, "bits": 16,
                "encoding": "pcm_s16le", "port": self.tcp_port,
            }).encode("utf-8"))
            # 首帧必须是 wifi_auth，否则断开（与 TcpBridgeServer 一致）。
            frame = self._recv(conn)
            if frame is None or frame.type != protocol.CONTROL:
                return
            auth = json.loads(frame.payload.decode("utf-8"))
            self.auth_frames.append(auth)
            token = str(auth.get("token") or "")
            code = str(auth.get("code") or "")
            ok = (token and token == self.token) or (code and code == self.pin)
            if not ok:
                self._send(conn, protocol.EVENT, json.dumps(
                    {"cmd": "wifi_auth", "ok": False}).encode("utf-8"))
                return
            if code and not token:
                self.token = TOKEN
            self._send(conn, protocol.EVENT, json.dumps(
                {"cmd": "wifi_auth", "ok": True, "token": self.token}).encode("utf-8"))
            self.auth_ok = True
            while not self._stop.is_set():
                self._send(conn, protocol.STATUS, json.dumps(
                    {"wifiOn": True, "wifiPaired": True, "clientIsLan": True},
                    ensure_ascii=False).encode("utf-8"))
                self.status_sent += 1
                time.sleep(0.05)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def main() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(("  [PASS] " if ok else "  [FAIL] ") + name + (f" — {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    port = _free_port()
    speaker = FakeSpeaker(port)
    speaker.start()
    time.sleep(0.2)
    print("假音箱已启动：UDP 17893 + TCP %d" % port)

    try:
        print("\n1) 局域网发现")
        found = wifi_pair.discover(timeout=1.2, targets=["127.0.0.1"], extra_ips=["127.0.0.1"])
        check("discover 找到设备", len(found) == 1, f"count={len(found)}")
        if found:
            dev = found[0]
            check("设备信息解析正确", dev.ip == "127.0.0.1" and dev.port == port,
                  dev.label())
            check("offer 里不含配对码", "code" not in dev.extra and "pin" not in dev.extra)

        print("\n2) 配对码校验")
        bad_ok, _bad_token, bad_msg = wifi_pair.pair("127.0.0.1", "000000", "TESTPC")
        check("错误配对码被拒绝", not bad_ok, bad_msg)
        good_ok, token, good_msg = wifi_pair.pair("127.0.0.1", PIN, "TESTPC")
        check("正确配对码返回 token", good_ok and token == TOKEN, good_msg)
        check("配对成功后音箱关闭配对窗口", speaker.pairing is False)

        print("\n3) TCP 首帧鉴权")
        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        sock.settimeout(5)
        hello = FakeSpeaker._recv(sock)
        check("先收到 HELLO 帧", hello is not None and hello.type == protocol.HELLO)
        payload = wifi_pair.auth_payload(token=token, pc_name="TESTPC")
        sock.sendall(protocol.encode_json(protocol.CONTROL, payload, seq=1))
        reply = FakeSpeaker._recv(sock)
        ok = False
        if reply is not None and reply.type == protocol.EVENT:
            body = json.loads(reply.payload.decode("utf-8"))
            ok = bool(body.get("ok"))
        check("token 鉴权通过", ok)
        status = FakeSpeaker._recv(sock)
        check("鉴权后收到 STATUS", status is not None and status.type == protocol.STATUS)
        check("STATUS 含局域网字段",
              status is not None and json.loads(status.payload.decode("utf-8")).get("clientIsLan") is True)
        sock.close()

        print("\n4) 用配对码在 TCP 上直接鉴权（免 UDP 配对）")
        speaker.token = ""          # 模拟"还没配对过"
        sock2 = socket.create_connection(("127.0.0.1", port), timeout=5)
        sock2.settimeout(5)
        FakeSpeaker._recv(sock2)
        sock2.sendall(protocol.encode_json(
            protocol.CONTROL, wifi_pair.auth_payload(code=PIN, pc_name="TESTPC"), seq=1))
        reply2 = FakeSpeaker._recv(sock2)
        body2 = json.loads(reply2.payload.decode("utf-8")) if reply2 else {}
        check("配对码鉴权通过并回发 token", bool(body2.get("ok")) and bool(body2.get("token")))
        sock2.close()

        print("\n5) 错误 token 必须被拒绝")
        speaker.token = TOKEN
        sock3 = socket.create_connection(("127.0.0.1", port), timeout=5)
        sock3.settimeout(5)
        FakeSpeaker._recv(sock3)
        sock3.sendall(protocol.encode_json(
            protocol.CONTROL, wifi_pair.auth_payload(token="deadbeef", pc_name="X"), seq=1))
        reply3 = FakeSpeaker._recv(sock3)
        body3 = json.loads(reply3.payload.decode("utf-8")) if reply3 else {}
        check("错误 token 被拒绝", not body3.get("ok", True))
        sock3.close()
    finally:
        speaker.stop()

    print()
    if failures:
        print(f"失败 {len(failures)} 项：" + "、".join(failures))
        return 1
    print("WiFi 配对自测全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
