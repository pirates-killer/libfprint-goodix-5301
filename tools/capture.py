#!/usr/bin/env python3
"""Milan F (27c6:5301) one-shot capture: reset, OTP, config, image -> PGM."""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gx

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(gx.LOGDIR, "frame")
d = gx.Device(verbose="-v" in sys.argv)
print("log:", d.logpath)
d.ping()
print("fw:", d.fw_version())
d.reset_sensor(False); time.sleep(0.01)
cid = gx.chip_id(d.read_reg(0, 4))
print(f"chip id: {cid:#x}")
assert cid == 0x2202, "not a Milan F sensor"
otp = d.read_otp()
print("otp params (tcode, diff, dac):", gx.otp_params(otp))
cfg = gx.milanf_config(otp)
print("config upload result:", d.upload_config(cfg))
flags, payload = gx.milanf_get_image(d)
print(f"image ack flags {flags.hex()}, payload {len(payload)} B, head {payload[:8].hex(' ')}")
open(out + ".raw", "wb").write(payload)
px = gx.milanf_frame(payload)
gx.write_pgm(out + ".pgm", px, gx.MILANF_W, gx.MILANF_H)
print(f"pixels {len(px)}, min {min(px)} max {max(px)} mean {sum(px)/len(px):.0f} -> {out}.pgm")
d.close()
