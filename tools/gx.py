"""Goodix 27c6:5301 (GF5288 sensor behind an HT32 "HT_APP" MCU) over CDC-ACM.

Wire format = goodix-fp-dump "wrapless" protocol, without GTLS:
  message  = cmd | size LE16 (= len(payload) + 1) | payload | csum
  cmd      = category << 4 | command << 1
  csum     = (0xAA - sum(cmd..payload)) & 0xFF, or 0x88 = "no checksum"
  transfer = 64-byte chunks; chunks after the first start with (cmd | 1).
             The MCU pads every IN chunk to 64 bytes with stale RAM.
Every host message is ACKed with b0 03 00 <cmd> <flags> <csum>.

Safety: only allow-listed commands are sent. Flash erase/write, option-byte
and PSK/production writes are refused at the lowest layer.
"""
import datetime
import os
import select
import struct
import termios
import time

CHUNK = 64

# cmd byte -> name. Anything not listed here is refused.
SAFE = {
    0x00: "nop",
    0x20: "get_image",
    0x32: "fdt_down",
    0x34: "fdt_up",
    0x36: "fdt_manual",
    0x60: "sleep_mode",
    0x70: "idle_mode",
    0x82: "read_reg",
    0x90: "upload_config",   # sensor config, RAM only (re-sent on every init)
    0xA2: "reset",           # only type 0 (sensor reset) is allowed, see reset()
    0xA6: "read_otp",
    0xA8: "fw_version",
    0xAE: "ec_control",      # sensor power on/off
    0xE4: "production_read",
    0xF2: "read_firmware",
    0xF6: "iap_version",
}
NEVER = {0xA4: "erase_app", 0xF0: "write_fw", 0xF4: "check_fw/commit",
         0xF8: "option_byte", 0xE2: "production_write", 0xE0: "psk_write"}

# protocol logs and images go here (override with GX_OUT)
LOGDIR = os.environ.get("GX_OUT", os.path.join(os.getcwd(), "gx-captures"))


class GxError(Exception):
    pass


class Msg:
    def __init__(self, cmd, payload):
        self.cmd, self.payload = cmd, payload

    @property
    def category(self):
        return self.cmd >> 4

    @property
    def command(self):
        return (self.cmd & 0xF) >> 1

    def __repr__(self):
        p = self.payload
        shown = p.hex(" ") if len(p) <= 48 else p[:48].hex(" ") + f" ... ({len(p)} B)"
        return f"<{self.cmd:#04x} {SAFE.get(self.cmd, '?')}: {shown}>"


def encode(cmd, payload, checksum=True):
    body = bytes([cmd]) + struct.pack("<H", len(payload) + 1) + payload
    return body + bytes([(0xAA - sum(body)) & 0xFF if checksum else 0x88])


class Device:
    def __init__(self, path="/dev/ttyACM0", log=True, verbose=False):
        self.verbose = verbose
        self.logf = None
        if log:
            os.makedirs(LOGDIR, exist_ok=True)
            name = "gx-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".log"
            self.logpath = os.path.abspath(os.path.join(LOGDIR, name))
            self.logf = open(self.logpath, "a")
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        a = termios.tcgetattr(self.fd)
        a[0] = a[1] = a[3] = 0
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[4] = a[5] = termios.B115200
        a[6][termios.VMIN] = 0
        a[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, a)
        self.buf = b""
        self.drain()

    # ---------- low level ----------
    def _log(self, s):
        if self.logf:
            self.logf.write(f"{time.monotonic():.3f} {s}\n")
            self.logf.flush()
        if self.verbose:
            print(s)

    def drain(self, secs=0.15):
        termios.tcflush(self.fd, termios.TCIFLUSH)
        junk = self._read_raw(secs)
        self.buf = b""
        if junk:
            self._log(f"drained {len(junk)} B: {junk[:64].hex(' ')}")

    def _read_raw(self, secs):
        out, end = b"", time.monotonic() + secs
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return out
            r, _, _ = select.select([self.fd], [], [], left)
            if r:
                try:
                    out += os.read(self.fd, 65536)
                except BlockingIOError:
                    pass

    def _chunk(self, timeout):
        end = time.monotonic() + timeout
        while len(self.buf) < CHUNK:
            left = end - time.monotonic()
            if left <= 0:
                raise GxError(f"timeout waiting for chunk (have {len(self.buf)} B: "
                              f"{self.buf.hex(' ')})")
            r, _, _ = select.select([self.fd], [], [], left)
            if r:
                try:
                    self.buf += os.read(self.fd, 65536)
                except BlockingIOError:
                    pass
        c, self.buf = self.buf[:CHUNK], self.buf[CHUNK:]
        return c

    def recv(self, timeout=2.0):
        data = self._chunk(timeout)
        cmd = data[0]
        size = struct.unpack("<H", data[1:3])[0]
        while len(data) < size + 3:
            c = self._chunk(timeout)
            if c[0] != (cmd | 1):
                raise GxError(f"bad continuation {c[0]:#04x} for {cmd:#04x} "
                              f"after {len(data)}/{size + 3} B")
            data += c[1:]
        data = data[:size + 3]
        csum = data[-1]
        want = (0xAA - sum(data[:-1])) & 0xFF
        if csum not in (0x88, want):
            raise GxError(f"bad checksum {csum:#04x} != {want:#04x} for {cmd:#04x}")
        m = Msg(cmd, data[3:-1])
        self._log(f"RX {m!r}")
        return m

    def send(self, cmd, payload, ack_timeout=0.5, checksum=True):
        if cmd in NEVER or cmd not in SAFE:
            raise GxError(f"refusing to send cmd {cmd:#04x} "
                          f"({NEVER.get(cmd, 'not allow-listed')})")
        data = encode(cmd, payload, checksum)
        self._log(f"TX <{cmd:#04x} {SAFE[cmd]}: {payload.hex(' ')}>")
        first = True
        while data:
            if first:
                chunk, data, first = data[:CHUNK], data[CHUNK:], False
            else:
                chunk, data = bytes([cmd | 1]) + data[:CHUNK - 1], data[CHUNK - 1:]
            os.write(self.fd, chunk.ljust(CHUNK, b"\x00"))
        ack = self.recv(ack_timeout)
        if ack.cmd != 0xB0 or not ack.payload or ack.payload[0] != cmd:
            raise GxError(f"expected ACK for {cmd:#04x}, got {ack!r}")
        return ack.payload[1:]

    def request(self, cmd, payload, timeout=2.0):
        self.send(cmd, payload)
        m = self.recv(timeout)
        if m.cmd != cmd:
            raise GxError(f"expected reply {cmd:#04x}, got {m!r}")
        return m.payload

    # ---------- commands (53x5 semantics) ----------
    def ping(self):
        self.send(0x00, b"\x00\x00")

    def fw_version(self):
        return self.request(0xA8, b"\x00\x00").split(b"\x00")[0].decode()

    def read_reg(self, addr, size, timeout=1.0):
        return self.request(0x82, b"\x00" + struct.pack("<HH", addr, size), timeout)

    def read_otp(self):
        return self.request(0xA6, b"\x00\x00")

    def reset_sensor(self, irq_status=False):
        """reset type 0 only (sensor reset, 20 ms). MCU resets are not allowed."""
        msg = 0b001 | (0b100 if irq_status else 0) | (20 << 8)
        self.send(0xA2, struct.pack("<H", msg))
        # HT_APP always replies (seen: 01 00 01), unlike 53x5 HTSEC.
        try:
            m = self.recv(1.0)
        except GxError:
            return None
        if m.cmd != 0xA2:
            raise GxError(f"expected reset reply, got {m!r}")
        return m.payload

    def ec_control(self, on):
        v = 1 if on else 0
        r = self.request(0xAE, bytes([v, v, 0]), 2.0)
        return int.from_bytes(r, "little")

    def upload_config(self, config):
        r = self.request(0x90, bytes(config), 1.0)
        return int.from_bytes(r, "little")

    def get_image_raw(self, req4, timeout=3.0):
        assert len(req4) == 4
        return self.request(0x20, req4, timeout)

    def sleep_mode(self):
        self.send(0x60, b"\x01\x00")

    def close(self):
        os.close(self.fd)
        if self.logf:
            self.logf.close()


def decode_12bit(data):
    """goodix-fp-dump tool.decode_image: 6 bytes -> 4 x 12-bit pixels."""
    img = []
    for i in range(0, len(data) - 5, 6):
        c = data[i:i + 6]
        img.append(((c[0] & 0xF) << 8) + c[1])
        img.append((c[3] << 4) + (c[0] >> 4))
        img.append(((c[5] & 0xF) << 8) + c[2])
        img.append((c[4] << 4) + (c[5] >> 4))
    return img


def write_pgm(path, pixels, width, height, maxval=4095):
    """Binary 16-bit PGM (P5)."""
    with open(path, "wb") as f:
        f.write(f"P5\n{width} {height}\n{maxval}\n".encode())
        f.write(b"".join(struct.pack(">H", p) for p in pixels[:width * height]))


# ---------------------------------------------------------------------------
# Milan F (chip 0x2202) specifics, learned from the Windows driver milanFusb.dll
# 1.0.33.600. Sensor 108 x 88, 12-bit.
# ---------------------------------------------------------------------------
MILANF_W, MILANF_H = 108, 88
_HERE = os.path.dirname(os.path.abspath(__file__))
MILANF_CONFIG = open(os.path.join(_HERE, "milanf_config.bin"), "rb").read()  # g_general[0]


def chip_id(raw4):
    """ChipRegRead swaps bytes per 16-bit word; id = b1' | b2'<<8 | b3'<<16."""
    s = bytes([raw4[1], raw4[0], raw4[3], raw4[2]])
    return s[1] | s[2] << 8 | s[3] << 16


def config_checksum(cfg):
    s = 0xA5A5
    for i in range(0, 0xFE, 2):
        s = (s + int.from_bytes(cfg[i:i + 2], "little")) & 0xFFFF
    cfg[0xFE:0x100] = ((-s) & 0xFFFF).to_bytes(2, "little")


def _patch_tag(cfg, base_idx, tag, lo=None, hi=None):
    base, size = cfg[base_idx], cfg[base_idx + 1]
    if not size:
        return
    i = base + 2
    for _ in range(((size - 1) >> 2) + 1):
        if int.from_bytes(cfg[i - 2:i], "little") == tag:
            if lo is not None:
                cfg[i] = lo
            if hi is not None:
                cfg[i + 1] = hi
        i += 4


def otp_params(otp):
    """CheckTcodeAndDiff: returns (tcode, diff, dac) or None for defaults."""
    dac = (otp[0x13] & 0x80) * 0x100 + otp[0x1F]   # driver: (b & 0xff80) * 0x100 + b
    if otp[0x16] and otp[0x16] + otp[0x17] == 0xFF:
        tcode = ((otp[0x16] >> 4) + 1) * 0x10
        diff = ((((otp[0x16] & 0xF) + 2) * 0x6400 // tcode & 0xFFFF) // 3) >> 4
        return tcode, diff, dac
    return None


def milanf_config(otp=None):
    cfg = bytearray(MILANF_CONFIG)
    p = otp_params(otp) if otp else None
    if p:
        tcode, diff, _ = p
        _patch_tag(cfg, 9, 0x5C, tcode & 0xFF, tcode >> 8)   # modify_image_tcode
        _patch_tag(cfg, 5, 0x82, hi=diff & 0xFF)             # modify_fdt_delta
    config_checksum(cfg)
    return bytes(cfg)


def _crc32_mpeg2(data):
    c = 0xFFFFFFFF
    for b in data:
        c ^= b << 24
        for _ in range(8):
            c = ((c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if c & 0x80000000 else (c << 1) & 0xFFFFFFFF
    return c


def _lfsr_prbs(p):
    """Literal port of lfsr_prbs (32-bit). Returns (word16, next_state)."""
    M = 0xFFFFFFFF
    u2 = (p >> 1 ^ p) & M
    u1 = ((((((((p >> 0xF & 0x2000 | p & 0x1000000) >> 1 | p & 0x20000) >> 2 |
              p & 0x1000) >> 3 | (p >> 7 ^ p) & 0x80000) >> 1 |
            (p >> 0xF ^ p) & 0x4000) >> 2 | p & 0x2000) >> 1 |
          (p >> 0xE ^ p) & 0x200) >> 1 | u2 & 0x40 | p & 0x20) >> 1
    lo8 = ((u1 & 0xFF) | (((p >> 0x14) & 0xFF) ^ ((p & 0xFF) * 2)) & 4 | p & 1) & 0xFF
    nxt = ((((u2 >> 0x1E) ^ (p >> 10 & 0xFF) ^ (p & 0xFF)) << 0x1F) | (p >> 1)) & M
    w = (((u1 >> 8) & 0xFFFF) |
         (((p >> 0x18) & 0xFF) ^ ((((p << 3) & M) >> 8) & 0xFFFF)) & 0x40 |
         (((p >> 0x11) & 0xFFFF) ^ (p & 0xFFFF)) & 8 |
         (((((p << 6) & M) >> 8) & 0xFFFF) ^ (((p >> 7) >> 8) & 0xFFFF)) & 1 |
         ((((p & 0x100) << 7) >> 8) & 0xFFFF))
    return (w + lo8 * 0x100) & 0xFFFF, nxt


def prbs_decrypt(data, seed=0x12345678):
    out = bytearray(data)
    st = seed
    for i in range(0, len(out) - 1, 2):
        w, st = _lfsr_prbs(st)
        v = int.from_bytes(out[i:i + 2], "little") ^ w
        out[i:i + 2] = v.to_bytes(2, "little")
    return bytes(out)


def milanf_frame(payload, decrypt=True):
    """payload = 0x20 reply payload. Returns 108*88 12-bit pixels or raises."""
    # driver: pData + 5, Length - 6, where pData = payload (header already stripped)
    body = payload[5:5 + (len(payload) + 1) - 6]
    d = body
    want = d[-2] << 24 | d[-1] << 16 | d[-4] << 8 | d[-3]
    got = _crc32_mpeg2(d[:-4])
    if want != got:
        raise GxError(f"frame CRC mismatch {want:#010x} != {got:#010x} (len {len(d)})")
    px = d[:-4]
    if decrypt:
        px = prbs_decrypt(px)
    return decode_12bit(px)


def milanf_get_image(dev, timeout=3.0):
    """SetMode(2): cmd 0x20 payload 01 00, then wait for the 0x20 reply."""
    flags = dev.send(0x20, b"\x01\x00")
    m = dev.recv(timeout)
    if m.cmd != 0x20:
        raise GxError(f"expected image, got {m!r}")
    return flags, m.payload
