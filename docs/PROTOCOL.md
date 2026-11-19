# Goodix 27c6:5301 ("Milan F") protocol notes

Everything here was learned from the Goodix Windows driver `milanFusb.dll`
1.0.33.600 (Windows Update Catalog, hardware ID `USB\VID_27C6&PID_5301`,
which also ships public debug symbols) and checked against a real device.
No Goodix code or firmware is included in this repository.

## Hardware

| | |
|---|---|
| USB | `27c6:5301`, full speed, manufacturer string "HTMicroelectronics", product "Goodix Fingerprint Device", serial "HTK32" |
| Interfaces | CDC-ACM: interface 0 = control (interrupt EP 0x82), interface 1 = data (bulk OUT 0x03, bulk IN 0x81). Linux binds `cdc_acm` (`/dev/ttyACM*`). |
| MCU firmware | `GF5288_HT_APP_10035` (the reply also contains other `GFxxxx_HT_APP_10035` names). `HT_APP` = no TLS, unlike the `HTSEC` firmware on 27c6:5385/5395. |
| Sensor | chip ID `0x2202` ("Milan F"), 108 x 88 pixels, 12-bit |

The Windows driver also knows chip IDs 0x2207, 0x2208 (Milan E/G, 176 x 64 / 176 x 54) and 0x2205 (Milan L, 132 x 112). Those are not supported here.

## Framing ("message pack", no TLS)

```
message  = cmd | size LE16 | payload | checksum
size     = len(payload) + 1
cmd      = category << 4 | command << 1
checksum = (0xAA - sum(cmd .. payload)) & 0xFF   (0x88 = "no checksum")
```

Messages travel in 64-byte packets. The first packet holds the start of the
message; every following packet starts with `cmd | 1` and carries 63 more
bytes. The host pads its packets to 64 bytes. The MCU always sends full
64-byte packets (padding is stale RAM) and follows them with zero-length
packets, which a raw USB reader must skip.

Every host message is acknowledged with
`b0 03 00 <cmd> <flags> <checksum>`. Flags bit 0 = ACK, bit 1 = the sensor
has no valid config (re-upload it).

## Commands used

| cmd | name | payload | reply |
|---|---|---|---|
| `0x00` | NOP | `00 00` | ACK only |
| `0xa8` | firmware version | `00 00` | NUL-terminated strings |
| `0xa2` | reset | `01 14` (sensor reset, 20 ms) | `01 00 01` (always sent on HT_APP) |
| `0x82` | read sensor register | `00 <addr LE16> <len LE16>` | register bytes, big-endian 16-bit words |
| `0xa6` | read OTP | `00 00` | 32 bytes |
| `0x90` | upload config | 256-byte config | `01 00` = accepted |
| `0x20` | get image | `01 00` | image payload (below) |
| `0x32/0x34/0x36` | finger detect down/up/manual | `op, 1, 12 x u16 base` | 28-byte FDT event (not used by the driver) |
| `0x60` | sleep | `01 00` | ACK |

Commands that write flash, erase the application, change option bytes or
write keys exist (`0xa4`, `0xf0`, `0xf4`, `0xf8`, `0xe0`, `0xe2`). The driver
and tools never send them.

Chip ID: read 4 bytes at register 0, swap each 16-bit pair, then
`id = b1 | b2 << 8 | b3 << 16`. Raw `02 a0 00 22` -> `0x2202`.

## Init sequence

1. NOP, firmware version.
2. Sensor reset (`0xa2 01 14`), wait for its reply.
3. Read chip ID, require `0x2202`.
4. Read OTP and derive calibration (Windows `CheckTcodeAndDiff`):
   - if `otp[0x16] != 0` and `otp[0x16] + otp[0x17] == 0xff`:
     `tcode = ((otp[0x16] >> 4) + 1) * 16`,
     `diff = ((((otp[0x16] & 0xf) + 2) * 0x6400 / tcode) / 3) >> 4`
   - patch the config: tag `0x5c` (value = tcode) in the section whose
     (offset, size) is at config bytes 9/10; tag `0x82` (high byte = diff) in
     the section at bytes 5/6. Sections are lists of `tag LE16, value LE16`.
5. Fix the config checksum: `0xa5a5 + sum of the first 127 LE16 words`,
   negated, stored in the last two bytes.
6. Upload the config (`0x90`).

The base config is the driver's `g_general[0]` table and is embedded in the
libfprint driver source.

## Image payload

Reply to `0x20` with `size - 1` = 14265 payload bytes:

```
payload[0:5]          header (ignored)
payload[5:5+14256]    pixel data, 108 x 88 x 12 bit
payload[14261:14265]  CRC32
```

- CRC: CRC-32/MPEG-2 (poly 0x04C11DB7, init 0xFFFFFFFF, MSB first, no final
  XOR) over the 14256 pixel bytes. Stored as bytes
  `b[-2] b[-1] b[-4] b[-3]`, most significant first.
- Descramble: XOR the pixel data, as little-endian 16-bit words, with the
  output of the Goodix `lfsr_prbs` generator seeded with `0x12345678` (see
  `prbs_decrypt` / `lfsr_prbs` in the driver).
- Unpack: every 6 bytes hold 4 pixels:
  ```
  p0 = (b0 & 0x0f) << 8 | b1     p1 = b3 << 4 | b0 >> 4
  p2 = (b5 & 0x0f) << 8 | b2     p3 = b4 << 4 | b5 >> 4
  ```

A finger lowers the readings (by 100 to 700 counts on average in our tests),
so `baseline - frame` gives a positive fingerprint image.

## Matching

108 x 88 pixels (about 5 x 4 mm) shows only 0 to 2 minutiae, so libfprint's
NBIS/bozorth3 cannot match it. The driver uses SIGFM: SIFT keypoints on a
locally normalised image, Lowe ratio test, then a count of match pairs whose
lengths and angles agree. In testing on one device, wrong fingers scored at
most 18 and the match threshold is 40.
