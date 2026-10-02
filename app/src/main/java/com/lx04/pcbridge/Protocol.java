package com.lx04.pcbridge;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

final class Protocol {
    static final String MAGIC = "LXB1";
    static final int HEADER_SIZE = 16;
    static final int PORT = 17890;
    static final int VIDEO_PORT = 17891;
    static final int TOAST_PORT = 17892;
    /** WiFi（局域网）配对用的 UDP 端口，见 WifiPairServer。 */
    static final int WIFI_PAIR_PORT = 17893;
    static final int MAX_PAYLOAD = 256 * 1024;

    static final byte HELLO = 0x01;
    static final byte HELLO_ACK = 0x02;
    static final byte AUDIO = 0x03;
    static final byte STATUS = 0x04;
    static final byte CONTROL = 0x05;
    static final byte PING = 0x06;
    static final byte PONG = 0x07;
    static final byte PLAY = 0x08;
    static final byte VIDEO = 0x09;
    static final byte VIDEO_ACK = 0x0A;
    static final byte FILE = 0x0B;
    static final byte EVENT = 0x0C;

    static final byte FLAG_MUTED = 0x01;

    static byte[] encode(byte type, byte flags, int seq, long timestampMs, byte[] payload) {
        if (payload == null) {
            payload = new byte[0];
        }
        ByteBuffer buf = ByteBuffer.allocate(HEADER_SIZE + payload.length);
        buf.order(ByteOrder.LITTLE_ENDIAN);
        buf.put(MAGIC.getBytes(StandardCharsets.US_ASCII));
        buf.put(type);
        buf.put(flags);
        buf.putShort((short) (seq & 0xFFFF));
        buf.putInt((int) (timestampMs & 0xFFFFFFFFL));
        buf.putInt(payload.length);
        buf.put(payload);
        return buf.array();
    }

    static Frame decodeHeader(byte[] header) {
        if (header == null || header.length < HEADER_SIZE) {
            return null;
        }
        ByteBuffer buf = ByteBuffer.wrap(header);
        buf.order(ByteOrder.LITTLE_ENDIAN);
        byte[] magic = new byte[4];
        buf.get(magic);
        if (magic[0] != 'L' || magic[1] != 'X' || magic[2] != 'B' || magic[3] != '1') {
            return null;
        }
        Frame frame = new Frame();
        frame.type = buf.get();
        frame.flags = buf.get();
        frame.seq = buf.getShort() & 0xFFFF;
        frame.timestampMs = buf.getInt() & 0xFFFFFFFFL;
        frame.payloadLength = buf.getInt();
        if (frame.payloadLength < 0 || frame.payloadLength > MAX_PAYLOAD) {
            return null;
        }
        return frame;
    }

    /** 从流里读一帧（帧头 + payload）。流结束返回 null，帧头非法抛 IOException。 */
    static Frame readFrame(java.io.InputStream in) throws java.io.IOException {
        byte[] header = new byte[HEADER_SIZE];
        if (!readFully(in, header)) {
            return null;
        }
        Frame frame = decodeHeader(header);
        if (frame == null) {
            throw new java.io.IOException("bad frame header");
        }
        byte[] payload = new byte[frame.payloadLength];
        if (frame.payloadLength > 0 && !readFully(in, payload)) {
            throw new java.io.IOException("short payload");
        }
        frame.payload = payload;
        return frame;
    }

    static boolean readFully(java.io.InputStream in, byte[] dest) throws java.io.IOException {
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

    /**
     * 增量帧读取器。
     *
     * <p>比一次性 {@link #readFrame} 多保留"已读进度"：socket 读超时
     * （SO_TIMEOUT → SocketTimeoutException）打断在帧头或负载中间时，已读字节
     * 不会丢，下次调用从断点继续。否则超时后重读会从错位处解析，魔数校验失败
     * 直接断链。
     */
    static final class Reader {
        private final java.io.InputStream in;
        private final byte[] header = new byte[HEADER_SIZE];
        private int headerOff;
        private byte[] payload = new byte[0];
        private int payloadOff;
        private Frame frame;

        Reader(java.io.InputStream in) {
            this.in = in;
        }

        /** 读下一帧；流结束返回 null；超时抛 SocketTimeoutException 并保留进度。 */
        Frame next() throws java.io.IOException {
            if (frame == null) {
                while (headerOff < HEADER_SIZE) {
                    int n = in.read(header, headerOff, HEADER_SIZE - headerOff);
                    if (n < 0) {
                        return null;
                    }
                    headerOff += n;
                }
                frame = decodeHeader(header);
                if (frame == null) {
                    throw new java.io.IOException("bad frame header");
                }
                payload = new byte[frame.payloadLength];
                payloadOff = 0;
            }
            while (payloadOff < payload.length) {
                int n = in.read(payload, payloadOff, payload.length - payloadOff);
                if (n < 0) {
                    return null;
                }
                payloadOff += n;
            }
            Frame done = frame;
            done.payload = payload;
            frame = null;
            headerOff = 0;
            payloadOff = 0;
            return done;
        }
    }

    static final class Frame {
        byte type;
        byte flags;
        int seq;
        long timestampMs;
        int payloadLength;
        byte[] payload;
    }

    private Protocol() {}
}
