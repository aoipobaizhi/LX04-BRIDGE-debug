package com.lx04.pcbridge;

final class BridgeState {
    volatile boolean usbConnected;
    volatile boolean usbAdb;
    volatile boolean clientConnected;
    volatile boolean recording;
    volatile boolean micMuted;
    volatile boolean spkMuted;
    volatile boolean upsideDown;
    volatile int sysRotation;
    volatile boolean uiHidden;
    volatile boolean lightTheme;
    volatile boolean screenMirror;
    volatile boolean toastOverlay;
    volatile boolean autoHideMute;
    volatile boolean bootStart;
    volatile boolean clockDate = true;
    volatile boolean clockHour = true;
    volatile boolean clockMinute = true;
    volatile boolean clockSecond = true;
    volatile boolean flushStatus;
    volatile String mirrorTitle = "";
    volatile String toastTitle = "";
    volatile String toastApp = "";
    volatile String toastBody = "";
    volatile String[] toastButtonIds = new String[0];
    volatile String[] toastButtonLabels = new String[0];
    volatile boolean permissionDenied;
    /** WiFi（局域网）配对相关状态，USB 模式下这些字段保持 false/空。 */
    volatile boolean wifiPairing;
    volatile boolean wifiOn;
    volatile boolean wifiPaired;
    volatile boolean clientIsLan;
    volatile String wifiIp = "";
    volatile String wifiPairCode = "";
    volatile float level;
    volatile float playLevel;
    volatile float volume = 1f;
    volatile float gain = 1f;
    volatile long frames;
    volatile long dropped;
    volatile int sampleRate = 48000;
    volatile int channels = 1;
    volatile String audioSource = "";
    volatile String androidRelease = "";
    volatile String pcName = "";
    volatile String apkVersion = "";
    volatile String headline = "等待 USB";
    volatile String detail = "请用数据线连接电脑并打开 USB 调试";

    volatile boolean pcStatsValid;
    volatile long pcStatsAt;
    volatile float pcCpu;
    volatile float pcCpuTemp = Float.NaN;
    volatile float pcGpu = Float.NaN;
    volatile float pcGpuTemp = Float.NaN;
    volatile float pcVram = Float.NaN;
    volatile float pcGpuWatts = Float.NaN;
    volatile float pcGpuFan = Float.NaN;
    volatile String pcGpuName = "";
    volatile float pcRam;
    volatile float pcRamUsed;
    volatile float pcRamTotal;
    volatile float pcDisk;
    volatile float pcDiskUsed;
    volatile float pcDiskTotal;
    volatile float pcDiskIo = Float.NaN;
    volatile String pcDiskName = "";
    volatile float pcNetDown;
    volatile float pcNetUp;
    volatile long pcUptime;
    volatile int pcCores;
    volatile long pcNowMs;
    volatile long pcNowAt;
    volatile int pcTzMin;
    final HudStyle hudStyle = new HudStyle();
    final SparkHistory sparks = new SparkHistory();

    boolean hasPcStats() {
        return pcStatsValid && pcStatsAt != 0
                && android.os.SystemClock.elapsedRealtime() - pcStatsAt < 12_000;
    }

    /** 上位机本次用的链路："usb" / "wifiadb" / "wifi"，空表示还没收到。 */
    volatile String linkVia = "";

    String formatLink() {
        if (clientIsLan || "wifi".equals(linkVia)) {
            return "WiFi 局域网";
        }
        if ("wifiadb".equals(linkVia)) {
            return "WiFi ADB";
        }
        if ("usb".equals(linkVia)) {
            return usbAdb ? "USB ADB" : "USB 已插入";
        }
        // 上位机还没告知链路：已连接但线拔了，只能是无线 ADB。
        if (clientConnected && !usbConnected) {
            return "WiFi ADB";
        }
        if (!usbConnected) {
            return "USB 未连接";
        }
        return usbAdb ? "USB ADB" : "USB 已插入";
    }

    String formatAudio() {
        String source = audioSource == null || audioSource.isEmpty() ? "" : " · " + audioSource;
        return sampleRate / 1000 + "kHz / 16bit / "
                + (channels == 1 ? "单声道" : channels + "声道") + source;
    }
}
