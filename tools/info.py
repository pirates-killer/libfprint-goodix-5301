#!/usr/bin/env python3
"""Read-only sensor info: firmware, chip ID, OTP. No resets, no writes."""
import struct, sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
import gx

d = gx.Device(verbose=True)
print("log:", d.logpath)
d.ping()
print("firmware:", d.fw_version())
cid = d.read_reg(0x0000, 4)
print("chip id raw:", cid.hex(" "), "u32 = %#x" % struct.unpack("<I", cid[:4])[0] if len(cid) >= 4 else "")
otp = d.read_otp()
print(f"OTP ({len(otp)} B):", otp.hex(" "))
d.close()
