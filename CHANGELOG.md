# 更新日志

## 新增：磁盘卡片"多盘"指标（最多 4 个盘的 IO / 占用率）

- **不是一个全局开关，而是卡片的一个大字指标**：长按磁盘卡片 → 大字里选「多盘」，或在电脑端样式编辑器里选。
  这样长按编辑、样式双向同步、标题/字号/配色全部照旧生效，不再是独立于卡片之外的一套逻辑。
- **排版**：卡片内每个盘一个独立格子（圆角底），左边盘符、右边数值，格子底部一条进度条（底栏）。
- **默认显示磁盘 IO**（`\LogicalDisk(X:)\% Disk Time`，和单盘 diskIo 同源），**短按卡片**在 IO 与占用率之间切换，
  卡片右上角标出当前模式（`IO` / `占用`）。
- **数据**：上位机在 `pc_stats` 里附带 `disks = [[盘符, IO%, 占用%], ...]`，最多 4 组；两个值一起发，
  音箱端切换时不用再问电脑。电脑端「多盘显示」开关或样式里有「多盘」卡片时都会供数据，
  没手选满 4 个盘时用其它固定盘自动补齐。
- 真机验证：IO 模式 `C: 3% / D: 0% / E: 19% / F: 7%`，点一下切到占用 `C: 76% / D: 90% / E: 84% / F: 12%`，
  颜色随占用率自动红绿变化，同一张卡不画折线、其它卡片不受影响。

## 第二轮修复（音量同步 / 自动重连 / 链路显示 / 后台占用）

### 修复

| 现象 | 原因 | 改动 |
|------|------|------|
| 连接后拖任务栏主音量，音箱响度不变；拖到 0 音箱照样出声（对照：先把 Hi-Fi Cable Input 设为默认设备再连接就正常） | `win_volume` 把"当前默认播放设备的音量接口"只缓存一次，而连接流程**先读音量、后切默认设备**，缓存永久绑在旧设备上 → 每 80 ms 读到的都是旧设备音量，差值恒为 0，一条 `volume` 指令都不发 | 缓存改为**按设备 id** 失效（`GetSpeakers()._dev.GetId()`）；`set_default_render()` 成功后主动 `win_volume.invalidate()`；首次 `_push_pc_volume(force=True)` 移到 `_apply_speaker_route()` **之后**；轮询 80 ms → ~400 ms |
| 无线 ADB 连接时，音箱端显示"USB 未连接"（明明已连上） | `usbConnected` 只反映物理 USB；`formatLink()` 见线拔了就返回"USB 未连接"，状态灯也按 `!usbConnected` 判红 | 上位机在会话建立/重连时下发新指令 `link`（`via` = `usb`/`wifiadb`/`wifi`）；音箱端据此显示"USB ADB / WiFi ADB / WiFi 局域网"，未收到时按"已连接但线拔了"兜底；状态灯改为**已连接即绿** |
| 空闲时会周期性断线，且断开后**再也不自动重连**（必须手动点连接） | ① socket 读超时 8 秒就判掉线，而 PING 只在"读到一帧之后"才发 → 音箱空闲不发帧时必然 8 秒断一次；② `BridgeClient.alive` 是全局标志，旧连接线程的 `finally` 会把新连接一起置死（表现为连上就断）；③ 拉起失败 8 次后 `_revive_gave_up` 把 `_session` 清成 False，之后永远不再重试 | 读超时改 2 秒并在超时时**发 PING 保活**（音箱回 PONG），连续 30 秒毫无回包才判掉线；帧中间超时不再丢已读字节；`_loop` 的 `finally` 只有"当前代次"才有权宣告断开；`_send` 失败不再全局判死；拉起失败改为**每 30 秒自动重试**（保留会话） |
| **上位机后台 CPU 占用高**（实测平均 11.7%、峰值 100%） | `win_volume` 每次读数都调 `pycaw.AudioUtilities.GetSpeakers()`，它内部每次都 `CreateDevice`（实测 **52 ms**）并新建 COM 枚举器（12 ms）= **56.9 ms/次**；旧代码 80 ms 轮询一次 ≈ **71% 一个核**，我上一轮改成 400 ms 轮询仍有 ~14% | 复用 COM 枚举器；默认设备 id **每 1.5 秒才核对一次**（3.9 ms），没变就直接用缓存（**0.042 ms**）；托盘/最小化时不再刷新看不见的电平条与状态同步；心跳 80 ms → 200 ms |
| 音箱端后台占用偏高 | 监视页每 50 ms 无条件全屏重绘（约 20 fps）；镜像解码线程一旦启动**永不退出**（`running` 没有任何地方置回 false） | 刷新率自适应：镜像/弹窗 16 ms、录音 50 ms、有电脑数据 120 ms、空闲 250 ms，且视图不可见时不重绘；解码线程空闲 15 秒自动退出，收到新帧自动重启；上位机侧音量 COM 轮询降到 ~400 ms |

### 验证

- **真机（LX04 / Android 8.1，无线 ADB）**
  - 音箱屏幕实测显示 `WiFi ADB`（左上状态点绿色），不再出现"USB 未连接"
  - 静默 **15 秒连接仍存活**（`alive=True`）；旧代码 8 秒即断
  - 用本机两个真实播放设备切换验证：音量接口缓存跟随新设备（`bb0ce2edd}` → `67bc3624a}`），测试后已恢复原设备
  - 连接顺序断言：`link` < `_apply_speaker_route` < `_push_pc_volume` ✓
- **回归测试**：模拟静默 11 秒不掉线且收到 3 个 PING；不关闭旧连接直接重连，新连接不被旧线程打死 ✓
- **上位机 CPU 实测**：
  - `win_volume.get_state()` **56.9 ms → 0.042 ms/次**（500 次调用 0.021 s，等价旧代码 28.4 s 的工作量）
  - 整个上位机进程（最小化到后台）：**平均 1.98% CPU、峰值 7.8%**；修复前同口径 offscreen 采样为**平均 11.7%、峰值 100%**
  - `pc_stats.snapshot()` 稳态 15 ms/次（其中 `psutil.net_io_counters()` 占 10 ms，每秒一次 ≈ 1.5%）——可接受，未改
- **编译**：APK debug 186,082 B；host 侧 `py_compile` 全部通过

## v141（新增 WiFi 连接方式与卡顿修复）

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

- `HudBackground.put` 持锁做 JPEG 解码 + 落盘，与 `onDraw` 同一把锁 → 上传背景时整帧卡住（本轮只降了重绘频率，锁没动）
- 镜像 17891 单独断线后不重连（静默黑屏）；`send_file` 超限静默丢弃却打印"已上传"
- `screen_mirror` 的 AccessLost 无退避（安全桌面下每帧重建 D3D11）；GDI 回退路径不画鼠标指针
- `toast_mirror` 兜底点击坐标算错（`left + right//2` 应为 `(left + right)//2`）
- `pc_stats` CPU 温度单位分支写反（ACPI 热区温度取不到）
- `hw_capture` 的 RIFF 头处理脆弱 + `_alive` 跨代共享（可能持续噪声或静默无声）
- `win_endpoint.GetMixFormat` 内存泄漏
- `WRITE_SETTINGS` 未授权时静默失败而 STATUS 仍回传已生效
- 中文字段的 JSON `null` 会被读成字符串 `"null"` 显示在屏幕上
