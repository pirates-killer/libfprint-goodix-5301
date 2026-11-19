#!/usr/bin/env python3
"""Capture a baseline, then frames for N seconds; keep the best finger frame."""
import os, sys, time, struct, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gx

SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 90
OUT = os.path.join(gx.LOGDIR, "finger")
os.makedirs(OUT, exist_ok=True)

def png(path, px, w=108, h=88):
    lo, hi = sorted(px)[len(px) // 100], sorted(px)[-len(px) // 100]
    rows = b"".join(b"\0" + bytes(max(0, min(255, int((px[y*w+x]-lo)*255/max(1, hi-lo))))
                                  for x in range(w)) for y in range(h))
    ch = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(rows)) + ch(b"IEND", b""))

d = gx.Device()
d.ping(); d.reset_sensor(False); time.sleep(0.01)
otp = d.read_otp(); d.upload_config(gx.milanf_config(otp))
grab = lambda: gx.milanf_frame(gx.milanf_get_image(d)[1])
base = [sum(v) / 3 for v in zip(grab(), grab(), grab())]
png(os.path.join(OUT, "base.png"), [int(v) for v in base])
print("baseline ok; touch the sensor now", flush=True)
best, n, t0 = (0, None), 0, time.time()
while time.time() - t0 < SECS:
    try:
        px = grab()
    except gx.GxError as e:
        print("frame error:", e, flush=True); d.drain(); continue
    diff = [base[i] - px[i] for i in range(len(px))]
    m = sum(diff) / len(diff)
    var = sum((x - m) ** 2 for x in diff) / len(diff)
    n += 1
    if n % 5 == 0 or var > best[0]:
        print(f"{time.time()-t0:5.1f}s frame {n}: mean shift {m:7.1f} var {var:9.0f}", flush=True)
    if var > best[0]:
        best = (var, px)
        gx.write_pgm(os.path.join(OUT, "best.pgm"), px, 108, 88)
        png(os.path.join(OUT, "best.png"), px)
        png(os.path.join(OUT, "best-minus-base.png"), [int(x) for x in diff])
print(f"done: {n} frames, best variance {best[0]:.0f}; files in {OUT}")
d.close()
