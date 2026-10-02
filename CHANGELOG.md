# 更新日志

## v141（本次未发布改动）

### 新增

**两种无线连接方式**（原 USB 方式不变）

| 方式 | 实现 | 能力 |
|------|------|------|
| WiFi · 无线 ADB | `adb tcpip 5555` + `adb connect 音箱IP:5555`，其余流程与 USB 完全相同 | 与数据线一致：硬件麦 tinycap 直采、小爱让麦、系统旋转、后台切换全可用 |
| WiFi · 直连 | 直接连 17890/17891/17892 | 不用 adb、不用 Shizuku；硬件麦直采 / 小爱让麦不可用，麦克风退回 App 采集 |

- **配对与鉴权**（直连模式）：UDP **17893** 广播发现 → 音箱屏幕显示 6 位配对码 → 电脑输入配对 → 得到 token（此后免码）→ 连上 17890 后首帧必须发 `wifi_auth`，否则 6 秒内被断开。配对码不随广播外发；连错 5 次冷却 30 秒；17891/17892 只接受已授权/已配对 IP。回环地址（USB / adb forward）永远自动放行。
- **新指令**：`wifi_pair`（开/关配对模式）、`wifi_forget`（双方忘掉配对；上位机点「清除配对」时下发）。
- **音箱端**：菜单里新增「WiFi 配对」开关，直接显示本机 IP 与配对码。
- **上位机**：新增「连接方式」卡片（三选一、IP 输入、扫描按钮、发现的设备列表、配对码输入、配对/清除配对、读出音箱 IP、激活无线 ADB）。
- **工具**：`host/wifi_pair.py`（发现/配对 CLI）、`host/check_wifi_pair.py`（模拟音箱的端到端自测）、`host/一键启动上位机.bat`、根目录 `启动上位机.bat` 支持未打包时直接启动开发版。

### 改进

- **上位机不再卡界面**（全部移到后台线程，结果回主线程填界面）：

  | 操作 | 改前（GUI 线程） | 改后（GUI 线程） | 后台耗时 |
  |------|------------------|------------------|----------|
  | 刷新设备 | 4 318 ms | 0.7 ms | ~4.1 s 填好列表 |
  | 连接 | ~50 000 ms | 1.1 ms | 3.6 s 真连上 |
  | 诊断探测 | 593 ms | 0.5 ms | — |
  | 冷启动 | 1 759 ms | 0.3 ms | — |

- 系统旋转、后台切换、激活无线 ADB 的 adb 调用也移出 GUI 线程（单次最坏 8 s / 25 s）。
- 删除启动时重复且同样阻塞的 `_boot_scan` / `_boot_apply` 路径。

### 修复

**上位机**

- `adb_usb._run` 用 `text=True` 按系统 ANSI（中文 Windows 为 GBK）解码 adb 输出，遇到非 GBK 字节时读取线程抛 `UnicodeDecodeError`，`stdout` 变空、`returncode` 失真 —— **所有 adb 调用结果都不可信**（实测"连不上"会被当成成功）。改为 `encoding="utf-8", errors="replace"`；`release_git.py` 同类问题一并修。
- `_release_single_instance()` 全文件从未调用：关闭后立刻重开，新实例静默退出、不显示窗口。
- `_shutdown_work` 用单个 `try` 包住整条清理链：`hw.stop()` 一抛异常就跳过 `_restore_render`，系统默认播放设备永久留在 CABLE 上（电脑没声音）。
- `_tick` 80 ms 心跳只有"重新挂定时器"在 try 里：中途一次异常就永久停摆（电平条不动、音量同步失效）。
- `QtLoop` 每次 `after()` 新建 `QTimer` 且从不销毁（心跳 12.5 次/秒、音频帧 100 次/秒）→ 持续泄漏。

**Android**

- 权限请求死循环：`onRequestPermissionsResult` 无条件再请求，用户点"拒绝"后授权页反复抢屏，应用无法进入。改为只请求一次，且**无麦克风权限也能启动服务**（播放与 HUD 不依赖录音）。
- 弹窗按钮走 UI 线程直写 socket：PC 侧不读 17892 时 `write` 无限阻塞 → ANR。改为队列 + 专用写线程。
- 三个 TCP 服务器 `running=true` 在绑定之前：`BindException` 被空 catch 吞掉后**永不重试且无日志**。
- `setReuseAddress` 在 `bind` 之后调用，完全无效（三个服务器）。
- 读线程死亡后 socket / client / `STATE.clientConnected` 不清理：屏幕永远显示"已连接"，却收不到任何控制指令。
- socket 读超时打断在帧中间时丢弃已读字节 → 帧错位 → 读线程退出。新增 `Protocol.Reader` 保留读取进度。
- `requestAudioFocus` 从不 `abandonAudioFocus`。

### 协议变更

- 新增 UDP 端口 **17893**（发现 / 配对，JSON + `magic: LXB1`）。
- CONTROL 新增：`wifi_auth`、`wifi_pair`、`wifi_forget`。
- STATUS 新增：`clientIsLan`、`wifiOn`、`wifiPairing`、`wifiPaired`、`wifiIp`、`wifiPort`、`wifiPairCode`。
- 详见 [protocol.md](protocol.md)。

### 升级注意

1. 需要**重新编译并安装 APK**（新增了鉴权，旧包没有闸门：局域网任意主机都能连）。
2. 音箱端跑一次 `host\install_apk.bat`，其中包含 `appops set com.lx04.pcbridge WRITE_SETTINGS allow` —— **系统旋转的前提**，只需一次、重启不丢。
3. 无线 ADB 模式在**音箱重启后**需要插一次线重新激活（Android 8.1 没有无线调试配对，只能 `adb tcpip`）。
4. 仓库里的 `.bat` 一律是纯英文 ASCII + CRLF：cmd 用系统 ANSI 代码页解析批处理，写入中文会在部分系统上被拆成乱码命令（典型报错 `'d'/'ho'/'exist' 不是内部或外部命令`）。自己改这些文件时请保持 ASCII。
5. 上位机依赖：`pip install -r host/requirements.txt`，或直接用 `host\一键启动上位机.bat`（会自动使用已装好依赖的 venv）。

### 验证情况

- **编译**：`:app:assembleDebug` 与 `:app:assembleRelease`（R8 混淆 + 资源压缩）均 BUILD SUCCESSFUL；debug ≈ 181 KB，release ≈ 69 KB。APK 元数据核对无误（`versionCode=141` = `VERSION.txt`）。
- **真机（LX04 / Android 8.1）**：
  - 无线 ADB 通道与直连通道各读到合法 HELLO；`adb tcpip 5555` 在 8.1 上可用
  - 配对 / 鉴权 **11/11 通过**：UDP 广播发现、配对码换 token、token 鉴权、错 token 被拒、完全不鉴权 6.0 s 被断开、配对窗口自动关闭
  - `wifi_forget` **7/7 通过**：清除后局域网 0.0 s 立即重新上锁，重新配对仍然可用
- **模拟环境**：`host\check_wifi_pair.py` 12/12；QML 离屏加载 0 警告；host 全部 `.py` 通过 `py_compile`。
- **性能**：见上表。

### 已知未处理

以下是代码审查中发现、但本次未改动的问题（按影响排序，供后续处理）：

- `HudBackground.put` 持锁做 JPEG 解码 + 落盘，与 `onDraw` 同一把锁 → 上传背景时整帧卡住
- `BridgeClient.alive` 是全局单标志，旧连接线程的 `finally` 可能把新连接打死并误报断线
- 镜像 17891 单独断线后不重连（静默黑屏）；`send_file` 超限静默丢弃却打印"已上传"
- `screen_mirror` 的 AccessLost 无退避（安全桌面下每帧重建 D3D11）；GDI 回退路径不画鼠标指针
- `toast_mirror` 兜底点击坐标算错（`left + right//2` 应为 `(left + right)//2`）
- `pc_stats` CPU 温度单位分支写反（ACPI 热区温度取不到）
- `hw_capture` 的 RIFF 头处理脆弱 + `_alive` 跨代共享（可能持续噪声或静默无声）
- `win_volume` 端点缓存永不失效（音量同步可能操作错设备）；`win_endpoint.GetMixFormat` 内存泄漏
- `WRITE_SETTINGS` 未授权时静默失败而 STATUS 仍回传已生效
- 中文字段的 JSON `null` 会被读成字符串 `"null"` 显示在屏幕上
