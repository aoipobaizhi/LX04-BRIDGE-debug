# LX04 PC Bridge

把小爱音箱触屏版 **LX04** 变成电脑的麦克风 + 扬声器 + 状态副屏。

音箱里跑一个很小的 APK（无 AndroidX、无 Play 服务），电脑上跑一个 Python 上位机。三条 TCP 通道分别负责**音频/音量/控制**（17890）、**屏幕镜像**（17891）、**系统弹窗**（17892），帧格式见 [protocol.md](protocol.md)。

## 它做什么

- 音箱采集麦克风，把 PCM 送给电脑；电脑上位机灌进 [VB-CABLE](https://vb-audio.com/Cable/)，其它软件把 `CABLE Output` 选成麦克风
- 电脑正在播放的声音经 [Hi-Fi Cable](https://vb-audio.com/Cable/) 环回，再送到音箱喇叭
- 音箱 800×480 屏幕显示：连接状态、右上角日期/时间（日期/时/分/秒可分别开关）、电脑 CPU / GPU 温度与占用、内存、所选磁盘、网速；底部两个按钮分别静音麦克风 / 扬声器
- 从屏幕右侧向左滑出菜单：「系统设置」（深色/浅色、静音按钮自动隐藏、时间项、开机自启、后台运行、WiFi 配对）、「监视页背景」（默认纯色或最多 3 张上位机上传的图，元素不透明度）、「屏幕镜像 / 状态监视」
- 样式双向同步：栏目的大字/多条小字、标题、颜色、字号，电脑上改或音箱上长按栏目改，两边实时一致
- 「系统旋转」锁定整机正向或倒转（音箱没有陀螺仪不会自动转）；「吊装倒转」只转桥接 HUD；「后台运行」把屏幕还给小爱、音频仍走后台
- 「同步系统弹窗」打开后，Windows 原生通知的标题/正文/按钮显示在音箱上（不是截图），点按钮等于点电脑上的通知
- 「屏幕镜像」把电脑画面投到音箱，可选投哪块显示器与码率（流畅 / 清晰 / 高清 / 最高）

> 官方固件的 Micro USB **默认不能装第三方 APK**。要用本项目，音箱需要已经能装普通 APK（社区官改 / X04G / Lineage 等），并使用**能传数据的 Micro USB 线**。

## 目录

| 路径 | 说明 |
|------|------|
| `app/` | LX04 上的 APK（Android 8.1+，`minSdk 26`） |
| `host/` | Windows 上位机（Python + PySide6/QML） |
| `host/一键启动上位机.bat` | 上位机开发版一键启动（优先用已装好依赖的 venv） |
| `host/install_apk.bat` | 装 APK + 授权 + 拉起后台服务 |
| `protocol.md` | 帧格式、UDP 配对、鉴权说明 |

## 三种连接方式

| 方式 | 怎么连 | 能力 |
|------|--------|------|
| **USB 数据线** | 插线 → 上位机点「连接」（自动 `adb forward`） | 全部功能 |
| **WiFi · 无线 ADB** | 插线时点一次「读出音箱 IP」（自动执行 `adb tcpip 5555`）→ 拔线 → 点「连接」 | **与数据线完全一致**：硬件麦直采、小爱让麦、系统旋转全部可用 |
| **WiFi · 直连** | 音箱「系统设置 → WiFi 配对」打开配对模式（屏幕显示 IP + 6 位配对码）→ 上位机扫描 → 输入配对码 → 配对 → 连接 | 不用 adb、不用装 Shizuku；硬件麦直采 / 小爱让麦不可用（麦克风走 App 采集）。系统旋转需要音箱已授权 `WRITE_SETTINGS`（见下） |

要点：

- Android 8.1 **没有** Android 11 的「无线调试配对」，所以无线 ADB 走的是老式 `adb tcpip` + `adb connect`，沿用电脑上已有的 adb 密钥，不需要再配对。代价：**音箱重启后 adbd 不再监听 TCP，需要再插一次线点一下「读出音箱 IP」**。
- 「WiFi · 直连」没有这个限制，任何时候都能连。
- 配对码只显示在音箱屏幕上、由人输入电脑，不随广播外发；配对成功得到的 token 存在两边，之后重连不再要配对码。
- 电脑点「清除配对」会同时让音箱忘掉 token（否则它的局域网监听会一直开着）。
- USB（回环地址）的客户端永远自动放行，不受配对影响。

## 电脑准备

1. Windows 10/11 64 位（可开着安全启动）
2. 官方 **VB-CABLE** 虚拟声卡（捐赠软件）。上位机只打开 [www.vb-cable.com](https://www.vb-cable.com/) 下载页，不附带安装包。装完后**重启**
3. 要把电脑音乐/视频接到音箱喇叭，再装官方 **Hi-Fi Cable**（同样来自 VB-Audio，和 VB-CABLE 不是同一根线）。**装完后重启**
4. 上位机已内置 adb，不需要装 Android SDK 也能连音箱

装好后 Windows 声音设置里会出现：

- **CABLE Input**：给上位机灌麦克风（不要设成电脑扬声器）
- **CABLE Output**：给微信 / QQ 当麦克风
- **Hi-Fi Cable Input**：连接后作为系统播放设备，声音进音箱喇叭

觉得好用请向 VB-Audio 捐赠。仓库和程序都不附带这两份安装包，商业分发见 [VB-Audio 授权说明](https://vb-audio.com/Services/licensing.htm)。

## 打开上位机

**方式 A（推荐，双击即可）**：

```text
host\一键启动上位机.bat
```

它会优先使用 `<工作区>\.tools\venv` 里已经装好依赖的 Python；找不到才退回系统 Python。

**方式 B（自己装依赖）**：

```text
host\install_deps.bat
host\start_host.bat
```

或手动：`python -m pip install -r host/requirements.txt`（PySide6 / sounddevice / pycaw / comtypes / psutil）。

**方式 C（打包成 EXE，不依赖本机 Python）**：

```text
python build_host_exe.py
```

生成 `dist/LX04-PC-Bridge-Host.exe`，之后双击根目录的 `启动上位机.bat` 即可（它会优先启动打包版）。

> 这些 `.bat` 一律是**纯英文 ASCII + CRLF** 保存的：cmd 用系统 ANSI 代码页解析批处理，文件里写中文会在某些系统上被拆成乱码命令（典型报错 `'d' 不是内部或外部命令`）。改这些文件时请保持 ASCII。

启动后：

1. 点「刷新设备」——**界面不会卡**，设备/音频/磁盘列表在后台约 4 秒填好
2. 选连接方式；USB 或无线 ADB 都应有 LX04 的序列号（无线是 `IP:5555`）
3. 点「连接」——同样是后台执行，状态栏显示「正在连接…」，几秒后变「已连接 LX04 v141」
4. 点「音箱试音」，音箱喇叭应能听到「嘀」
5. 在微信 / QQ / 语音输入里把麦克风选成 **CABLE Output**；彻底退出再打开这些软件，避免缓存旧设备
6. 电脑里的音乐/视频会从音箱出声（需已装 Hi-Fi Cable 并重启）。断开后系统扬声器会改回原来的设备

## 装到音箱

1. 音箱打开 **USB 调试**
2. 数据线连电脑，`设备管理器` 里应能看到 ADB 设备
3. 运行：

```text
host\install_apk.bat
```

它做的事（等价手动命令）：

```text
adb install -r -t app/build/outputs/apk/debug/app-debug.apk
adb shell pm grant com.lx04.pcbridge android.permission.RECORD_AUDIO
adb shell appops set com.lx04.pcbridge WRITE_SETTINGS allow
adb shell am start-foreground-service -n com.lx04.pcbridge/.BridgeService
```

`WRITE_SETTINGS` 这条**只差一次**：授权后系统旋转才能写进系统设置，且**重启不丢**。没授权时「系统旋转」只会转 App 自己的画面，整机不转。

## 编译 APK

用 Android Studio 打开仓库根目录（JDK 17+），**Build > Build APK(s)**；命令行：

```text
gradlew.bat :app:assembleDebug
```

产物在 `app/build/outputs/apk/debug/app-debug.apk`。构建脚本会检查 APK 是否超过 **300MB**（正常几 MB）。

本仓库实测：debug 约 181 KB，release（R8 混淆 + 资源压缩）约 69 KB。

## 常见问题

| 现象 | 原因 / 处理 |
|------|-------------|
| 双击 bat 报 `'d' / 'ho' / 'exist' 不是内部或外部命令` | 该 bat 被用 UTF-8 存了中文。仓库里的 bat 已改成纯 ASCII；自己改回来时注意 |
| 双击启动后没反应，或提示已有实例 | 上位机是单实例程序，第二次启动会把已有窗口弹到前台；若刚关闭又立刻启动，稍等 1～2 秒再点 |
| 无线 ADB 连不上（`adb 没有监听 TCP`） | 音箱重启过。插一次线，点「读出音箱 IP」重新激活，再拔线 |
| 配对码模式连不上 | 音箱上要先把「WiFi 配对模式」打开（屏幕会显示 IP + 配对码）；确认手机和电脑在同一网段 |
| 系统旋转只转了 App 画面 | 音箱还没授权 `WRITE_SETTINGS`，跑一次 `host\install_apk.bat` |
| 上位机提示找不到 VB-CABLE | 装完虚拟声卡要**重启**；上位机「连接诊断」里能看到各通道状态 |
| adb 报 `cannot open ...\adb.log: Permission denied` | 少见，一般是 adb server 被异常终止后 `%TEMP%` 不可写。把环境变量 `TEMP`/`TMP` 指到可写目录后执行 `adb start-server` |
| 音箱录到静音 | 原版小爱占着麦克风。改版 ROM / 关掉语音助手后最稳；上位机「麦克风」关掉即可不用麦克风 |

## 电脑状态怎么来的

上位机每秒采一次，经连接通道推到音箱。

| 项目 | 来源 | 分发时要不要额外东西 |
|------|------|----------------------|
| CPU / 内存占用、磁盘容量、网速、开机时长 | 打进 EXE 的 `psutil`，没有则退回 Windows API | 不用 |
| 磁盘 IO、部分 ACPI 温度、核显占用 | 系统自带 PDH | 不用 |
| NVIDIA 占用 / 温度 / 功耗 / 风扇 | 本机显卡驱动的 `nvml.dll` | 有驱动即可 |
| AMD 占用 / 温度 | 本机显卡驱动的 `atiadlxx.dll` | 有驱动即可 |
| CPU 封装温度 | 本机若开着 MSI Afterburner 就读它的共享内存 | **可选**，读不到就不显示（不会发假的 27°C） |

不要把 Afterburner、HWiNFO、LibreHardwareMonitor 打进安装包。

## 相对原版的变化

- **新增两种连接方式**：无线 ADB、直连（UDP 17893 发现 + 6 位配对码 + token，17890 首帧 `wifi_auth` 鉴权，17891/17892 按已授权 IP 放行）
- **上位机不再卡界面**：刷新设备（实测 4.3 s）、连接（实测 ~50 s）、诊断探测、系统旋转、后台切换、激活无线 ADB 全部移到后台线程，结果回主线程填界面
- **修掉的若干问题**：adb 输出按 GBK 解码崩溃导致所有 adb 结果不可信；权限请求死循环；UI 线程写 socket 导致 ANR；TCP 服务绑定失败后永不重试；`SO_REUSEADDR` 用错位置；读线程死亡后状态不清；超时打断半包导致帧错位；QTimer 每帧泄漏；单实例互斥体未释放；清理链一步异常就跳过恢复播放设备；心跳一次异常永久停摆；音频焦点未释放

## 硬件与系统

| 项目 | LX04 |
|------|------|
| 芯片 | MT8167，约 1GB 内存 |
| 屏幕 | 3.97 寸，800×480，横屏 |
| 麦克风 | 顶部双麦 |
| 接口 | Micro USB（刷机/开调试后可走数据） |
| 系统 | 原版偏 Android 8.1；国际版 X04G 为 Android 10。本 APK `minSdk 26`，两种都能装 |

## 体积约束

- APK 硬限制：≤ 300MB（Gradle 超限会失败）
- 实际：不引入大型依赖，release + minify 预期 **&lt; 5MB**

## 许可

原创源码以 [Apache License 2.0](LICENSE) 发布。第三方仍走各自协议，见 [NOTICE](NOTICE)。VB-CABLE / Hi-Fi Cable 是 VB-Audio 的捐赠软件，不在 Apache 范围内。
