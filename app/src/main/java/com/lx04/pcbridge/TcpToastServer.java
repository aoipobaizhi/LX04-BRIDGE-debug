package com.lx04.pcbridge;

import android.os.SystemClock;

import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

final class TcpToastServer {
    interface Callback {
        void onControl(JSONObject json);
    }

    private final Callback callback;
    private final AtomicInteger seq = new AtomicInteger();
    private final Object outLock = new Object();
    private volatile boolean running;
    private ServerSocket server;
    private Thread acceptThread;
    private volatile Socket client;
    private volatile OutputStream out;
    private final java.util.concurrent.ArrayBlockingQueue<byte[]> outbound =
            new java.util.concurrent.ArrayBlockingQueue<>(8);
    private Thread writerThread;

    TcpToastServer(Callback callback) {
        this.callback = callback;
    }

    synchronized void start() {
        if (running) {
            return;
        }
        running = true;
        acceptThread = new Thread(this::acceptLoop, "lx04-toast");
        acceptThread.start();
        writerThread = new Thread(this::writeLoop, "lx04-toast-out");
        writerThread.setDaemon(true);
        writerThread.start();
    }

    synchronized void stop() {
        running = false;
        closeQuietly(client);
        client = null;
        synchronized (outLock) {
            out = null;
        }
        if (writerThread != null) {
            writerThread.interrupt();
            writerThread = null;
        }
        outbound.clear();
        if (server != null) {
            try {
                server.close();
            } catch (Exception ignored) {
            }
            server = null;
        }
        if (acceptThread != null) {
            acceptThread.interrupt();
        }
    }

    boolean connected() {
        return client != null && out != null;
    }

    boolean sendEvent(JSONObject json) {
        if (json == null) {
            return false;
        }
        byte[] payload = json.toString().getBytes(StandardCharsets.UTF_8);
        byte[] frame = Protocol.encode(Protocol.EVENT, (byte) 0, seq.incrementAndGet(),
                SystemClock.elapsedRealtime(), payload);
        if (out == null) {
            return false;
        }
        // 只入队，交给专用写线程发送。
        // 以前是在调用线程里直接 write+flush：音箱上点弹窗按钮走的是 UI 线程，
        // PC 侧一旦不读 17892，写阻塞就会变成 ANR。
        if (!outbound.offer(frame)) {
            outbound.poll();
            outbound.offer(frame);
        }
        return true;
    }

    private void writeLoop() {
        while (running) {
            byte[] frame;
            try {
                frame = outbound.poll(200, java.util.concurrent.TimeUnit.MILLISECONDS);
            } catch (InterruptedException exc) {
                break;
            }
            if (frame == null) {
                continue;
            }
            try {
                synchronized (outLock) {
                    OutputStream stream = out;
                    if (stream == null) {
                        continue;
                    }
                    stream.write(frame);
                    stream.flush();
                }
            } catch (Exception ignored) {
                // 写失败保持静默：上层随时可以用 17890 回退通道。
            }
        }
    }

    private void acceptLoop() {
        try {
            // SO_REUSEADDR 必须在 bind 之前设置，构造带端口的 ServerSocket 已经绑过了。
            ServerSocket bound = new ServerSocket();
            bound.setReuseAddress(true);
            bound.bind(new java.net.InetSocketAddress(InetAddress.getByName("0.0.0.0"), Protocol.TOAST_PORT), 1);
            server = bound;
            if (!running) {
                closeQuietly(bound);
                return;
            }
            while (running) {
                Socket socket;
                try {
                    socket = bound.accept();
                } catch (Exception e) {
                    if (!running) {
                        break;
                    }
                    continue;
                }
                if (!WifiPairServer.INSTANCE.acceptPeer(socket)) {
                    closeQuietly(socket);
                    continue;
                }
                closeQuietly(client);
                client = socket;
                handleClient(socket);
                if (client == socket) {
                    client = null;
                }
                synchronized (outLock) {
                    out = null;
                }
            }
        } catch (Exception ignored) {
        } finally {
            // 绑定失败时复位，否则 running 永远为 true，start() 再也不重试。
            running = false;
        }
    }

    private void handleClient(Socket socket) {
        try {
            socket.setTcpNoDelay(true);
            socket.setSoTimeout(0);
            try {
                socket.setReceiveBufferSize(8 * 1024);
                socket.setSendBufferSize(8 * 1024);
            } catch (Exception ignored) {
            }
            InputStream in = socket.getInputStream();
            OutputStream stream = socket.getOutputStream();
            synchronized (outLock) {
                out = stream;
            }
            byte[] header = new byte[Protocol.HEADER_SIZE];
            while (running && client == socket && !socket.isClosed()) {
                if (!readFully(in, header)) {
                    break;
                }
                Protocol.Frame frame = Protocol.decodeHeader(header);
                if (frame == null) {
                    break;
                }
                byte[] payload = new byte[frame.payloadLength];
                if (frame.payloadLength > 0 && !readFully(in, payload)) {
                    break;
                }
                if (frame.type == Protocol.PING) {
                    byte[] pong = Protocol.encode(Protocol.PONG, (byte) 0, frame.seq,
                            SystemClock.elapsedRealtime(), new byte[0]);
                    synchronized (outLock) {
                        if (out != null) {
                            out.write(pong);
                            out.flush();
                        }
                    }
                    continue;
                }
                if (frame.type != Protocol.CONTROL || payload.length == 0) {
                    continue;
                }
                try {
                    callback.onControl(new JSONObject(new String(payload, StandardCharsets.UTF_8)));
                } catch (Exception ignored) {
                }
            }
        } catch (Exception ignored) {
        } finally {
            synchronized (outLock) {
                if (client == socket) {
                    out = null;
                }
            }
            closeQuietly(socket);
        }
    }

    private static boolean readFully(InputStream in, byte[] dest) throws Exception {
        int off = 0;
        while (off < dest.length) {
            int n = in.read(dest, off, dest.length - off);
            if (n < 0) {
                return false;
            }
            off += n;
        }
        return true;
    }

    private static void closeQuietly(Socket socket) {
        if (socket == null) {
            return;
        }
        try {
            socket.close();
        } catch (Exception ignored) {
        }
    }

    private static void closeQuietly(ServerSocket socket) {
        if (socket == null) {
            return;
        }
        try {
            socket.close();
        } catch (Exception ignored) {
        }
    }
}
