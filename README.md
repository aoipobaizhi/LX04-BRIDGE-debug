# LX04-BRIDGE-debug

本仓库是 [ndpyzwy-0w0/LX04-BRIDGE](https://github.com/ndpyzwy-0w0/LX04-BRIDGE) 的 fork，分支 `debug`。

> **这个 README 讲的是本 fork 相对上游修了哪些 bug、加了哪些功能。**
> 上游原版的项目说明（功能、安装、编译、硬件参数等）已原样保留在 **[README-UPSTREAM.md](README-UPSTREAM.md)**；
> 逐条改动记录见 **[CHANGELOG.md](CHANGELOG.md)**。

---

## 一、新增功能

### 1. WiFi · 无线 ADB（推荐）

**解决什么问题**：原来必须插着 Micro USB 数据线才能用，音箱一动就得拔插。

**原理**：Android 8.1 **没有** Android 11 才有的「无线调试配对」，但 `adb tcpip` 从很早就支持——它把音箱上的 `adbd` 重启到 TCP 模式，之后电脑直接 `adb connect 音箱IP:5555` 就能用同一套 adb 隧道。因为沿用电脑上已有的 adb 密钥，**不需要重新配对**，也不用装 Shizuku。

**怎么用**：

1. 数据线插着音箱（这一次必须插）
2. 上位机「连接方式」选 **WiFi · 无线 ADB**
3. 点 **「读出音箱 IP」** —— 它会自动执行 `adb tcpip 5555`，并把音箱的局域网 IP 填好
4. **拔掉数据线**，点「连接」

**能力**：与数据线**完全一致** —— 硬件麦 `tinycap` 直采、`stop mivpm` 小爱让麦、系统旋转、后台切换都能用。

**代价**：音箱**重启后** `adbd` 不再监听 TCP，需要再插一次线点一下「读出音箱 IP」。想彻底免插线，只能在已 root 的音箱上设 `persist.adb.tcp.port=5555`。

### 2. WiFi · 直连（配对码模式）

**解决什么问题**：手边没有数据线、也不想装 Shizuku 时，仍然能用。

**原理**：电脑直接连音箱的三条 TCP 口（17890 / 17891 / 17892，音箱端本来就监听 `0.0.0.0`），配对和鉴权是新增的一层：

| 步骤 | 说明 |
|---|---|
| 发现 | 电脑向 UDP **17893** 广播探测，音箱回一条 `offer`（含型号、IP、端口、是否正在配对）——**不含配对码** |
| 配对 | 音箱屏幕显示 **6 位配对码**，人工输入电脑；对了一次就发一个 32 位 `token`，此后免码 |
| 鉴权 | 连上 17890 后**首帧必须**发 `{"cmd":"wifi_auth", token 或配对码}`，否则 6 秒内断开 |
| 收口 | 17891 / 17892 只接受已授权或已配对的 IP；回环地址（USB / adb forward）永远自动放行 |

**安全设计**：配对码只显示在音箱屏幕上、不随广播外发；连错 5 次冷却 30 秒；上位机点「清除配对」会同时让音箱忘掉 token（否则它的局域网监听会一直开着）。

**能力**：不用 adb，所以**有降级** —— 硬件麦直采、小爱让麦不可用（麦克风退回 App 的 AudioRecord 采集）；「系统旋转」要求音箱已授权 `WRITE_SETTINGS`（`host\install_apk.bat` 里已经包含这条授权，只需一次、重启不丢）。

### 3. 上位机界面对应改动

- 新增「**连接方式**」卡片：三选一、IP 输入、扫描局域网设备并列出、配对码输入、配对 / 清除配对、读出音箱 IP
- 新增 `host\一键启动上位机.bat`：自动使用已装好依赖的 venv，双击即用
- 「设备」卡片会按当前连接方式显示 USB 序列号或 WiFi 地址

### 4. 协议新增（详见 protocol.md）

- UDP **17893**：发现 / 配对报文
- CONTROL 新增：`wifi_auth`、`wifi_pair`、`wifi_forget`
- STATUS 新增：`clientIsLan`、`wifiOn`、`wifiPairing`、`wifiPaired`、`wifiIp`、`wifiPort`、`wifiPairCode`

---

## 二、修复的 bug

### 上位机（Python）

| 现象 | 原因 |
|---|---|
| **所有 adb 调用结果都不可信**：设备明明连不上却报成功、状态判断随机出错 | `subprocess` 用 `text=True`，按系统 ANSI（中文 Windows 是 GBK）解码 adb 输出；遇到非 GBK 字节时读取线程抛 `UnicodeDecodeError`，`stdout` 变空、`returncode` 失真。改为 `utf-8 + errors="replace"`（`release_git.py` 同类问题一并修） |
| 关闭上位机后立刻重开，**新实例静默退出、不显示窗口** | `_release_single_instance()` 全文件从未调用，命名互斥体要等进程真正结束才释放 |
| 退出后**电脑没声音**（默认播放设备留在 CABLE 上） | `_shutdown_work` 用一个大 `try` 包住整条清理链，`hw.stop()` 一抛异常就跳过了 `_restore_render` |
| 界面卡住后**电平条不动、音量同步失效、状态栏不再更新**，只能重启 | `_tick` 80ms 心跳只有"重新挂定时器"那句在 `try` 里，中途任何异常都会让心跳永久停摆且无日志 |
| 长时间挂着内存持续增长 | `QtLoop` 每次 `after()` 新建 `QTimer` 却从不销毁（心跳 12.5 次/秒、音频帧 100 次/秒） |
| 点「刷新设备」界面**卡死 4 秒多**，点「连接」卡死几十秒 | 设备枚举（COM 端点约 4.9 s）+ `adb devices`（异常时 8 s 超时）+ 三通道握手全部跑在 GUI 线程上。现已全部移入工作线程，结果回主线程填界面；实测刷新 **4318 ms → 0.7 ms**、连接 **约 50000 ms → 1.1 ms**（后台 3.6 s 完成） |
| `install_apk.bat` 双击报 `'d' / 'ho' / 'exist' 不是内部或外部命令` | 批处理文件用 UTF-8 存了中文，cmd 按 ANSI 代码页解析会把命令行拆碎。改为纯 ASCII + CRLF |
| `install_apk.bat` 找不到 APK 时仍去安装一个不存在的文件 | `for %%F in ("字面路径")` 对不存在的文件也会赋值，导致两个回退分支永不执行。改用 `if exist` |
| 装完 APK 后「系统旋转」整机不转 | 缺 `appops set ... WRITE_SETTINGS allow` 授权，脚本里已补上 |

### 音箱端（Android）

| 现象 | 原因 |
|---|---|
| 用户点「拒绝」录音权限后，**授权页反复弹、应用进不去** | `onRequestPermissionsResult` 无条件再次 `requestPermissions`，形成死循环。改为只请求一次；并且**没有录音权限也能启动服务**（播放与 HUD 本来不依赖录音） |
| 点音箱上的弹窗按钮时界面卡死（ANR 风险） | `TcpToastServer` 在调用线程（UI 线程）里直接 `write + flush` socket；PC 侧不读 17892 时写满缓冲即阻塞。改为队列 + 专用写线程 |
| 音箱端服务对外**完全连不上，而且没有任何日志** | 三个 TCP 服务器都是先把 `running = true` 再建 socket，`BindException` 被空 `catch` 吞掉后 `start()` 永远直接 return，再也不会重试 |
| 端口复用没生效，重启服务可能绑不上 | `setReuseAddress(true)` 写在 `new ServerSocket(port, ...)` **之后**，bind 已经完成。改为 `new ServerSocket()` → `setReuseAddress` → `bind` |
| 音箱显示"已连接"，但静音/样式/音量**所有控制指令都失灵且不自愈** | 读线程死亡后 socket 不关、`client` 不清、`STATE.clientConnected` 仍是 true。现在读线程退出时会关 socket、清状态并回调断开 |
| 偶发断连且再也连不上 | socket 读超时打断在**帧中间**时已读字节被丢弃，下次从错位处解析，魔数校验失败直接断链。新增带进度的 `Protocol.Reader`，超时只发 PING、不丢字节 |
| 音频焦点泄漏，其它播放器一直被判定为"被抢占" | `requestAudioFocus` 从不 `abandonAudioFocus` |

---

### 第二轮修复（音量同步 / 自动重连 / 链路显示 / 后台占用）

| 现象 | 原因 | 改动 |
|------|------|------|
| **拖任务栏主音量，音箱响度不变**；拖到 0 音箱照样出声 | `win_volume` 把"默认播放设备的音量接口"只缓存一次，而连接流程先读音量、后切默认设备 → 缓存永久绑在旧设备上，读到的永远是不变的旧值，一条 `volume` 指令都不发 | 缓存改为按**设备 id** 失效；切换默认设备成功后主动清缓存；首次读音量移到 `_apply_speaker_route()` 之后；轮询 80 ms → ~400 ms |
| **无线 ADB 时音箱显示"USB 未连接"** | `usbConnected` 只表示物理 USB；链路文案与状态灯都按它判断 | 新增 CONTROL `link`（`via` = `usb`/`wifiadb`/`wifi`），音箱据此显示"USB ADB / WiFi ADB / WiFi 局域网"；状态灯改为已连接即绿 |
| **空闲时周期性断线，断了以后不再自动重连** | 读超时 8 秒就判掉线，而 PING 只在读到帧后才发；`BridgeClient.alive` 是全局标志，旧连接线程会打死新连接；拉起失败 8 次后清掉 `_session` 永久放弃 | 读超时 2 秒 + 超时发 PING 保活（音箱回 PONG），30 秒无响应才判掉线；帧中间超时不丢字节；只有当前代次能宣告断开；失败后每 30 秒自动重试 |
| **上位机后台 CPU 占用高**（实测平均 11.7%） | 音量读取每次都重建 COM 设备对象（52 ms）+ 新建枚举器（12 ms），80 ms 轮询 ≈ 71% 一个核 | 复用枚举器 + 设备 id 每 1.5 秒核对一次（3.9 ms），未变就用缓存（0.042 ms）；托盘时不刷新看不见的电平条；心跳 80 ms → 200 ms。实测后台 **1.98%** |
| **音箱端后台占用偏高** | 监视页每 50 ms 无条件全屏重绘（约 20 fps）；镜像解码线程永不退出 | 刷新率自适应（镜像 16 ms / 录音 50 ms / 有数据 120 ms / 空闲 250 ms）+ 不可见不重绘；解码线程空闲 15 秒自动退出 |

## 三、验证情况

- **上位机 CPU**：音量读取 56.9 ms → **0.042 ms**/次；最小化后台整个进程 **平均 1.98% / 峰值 7.8%**（修复前平均 11.7% / 峰值 100%）
- **编译**：`:app:assembleDebug` 186,082 B、`:app:assembleRelease`（R8 混淆 + 资源压缩）70,416 B，均构建成功
- **第二轮实测**：音箱屏幕显示 `WiFi ADB`（不再显示"USB 未连接"）；静默 15 秒连接仍存活（旧代码 8 秒即断）；切换默认播放设备后音量接口缓存跟随新设备；模拟静默 11 秒不掉线并收到 3 个 PING
- **真机 LX04（Android 8.1）**：
  - 无线 ADB 通道与直连通道各读到合法 HELLO 帧
  - 配对 / 鉴权 **11/11 通过**：UDP 广播发现、配对码换 token、token 鉴权、错误 token 被拒、完全不鉴权 6.0 s 被断开、配对窗口自动关闭
  - 清除配对 `wifi_forget` **7/7 通过**：清除后局域网 0.0 s 立即重新上锁，重新配对仍可用
  - 已授权 `WRITE_SETTINGS`，系统旋转在直连模式下也能生效
- **模拟环境**：`host\check_wifi_pair.py` 12/12、QML 离屏加载 0 警告、host 全部 `.py` 通过 `py_compile`

---

## 四、升级注意

1. **必须重新安装 APK**：旧包没有鉴权闸门，局域网里任意主机都能连上音箱。
2. 装完跑一次 `host\install_apk.bat`（内含 `RECORD_AUDIO` 与 `WRITE_SETTINGS` 授权）。
3. 无线 ADB 模式在**音箱重启后**需要插一次线重新激活；直连模式不需要。
4. 仓库里的 `.bat` 一律是**纯英文 ASCII + CRLF**，修改时请保持，否则 cmd 会把中文解析成乱码命令。
5. 上位机依赖：用 `host\一键启动上位机.bat`，或先 `pip install -r host/requirements.txt`。

## 五、已知未处理

代码审查里还发现了一些问题（多为性能/健壮性，不影响本次功能），清单见 [CHANGELOG.md](CHANGELOG.md) 的「已知未处理」一节。
