# Goodix 27c6:5301 fingerprint reader on Linux

A libfprint driver for the **Goodix 27c6:5301** fingerprint reader
("Milan F", GF5288-family sensor), which has never had a Linux driver
([libfprint #161](https://gitlab.freedesktop.org/libfprint/libfprint/-/issues/161)).
With it, `fprintd` can enroll fingers, and you can use your fingerprint for
`sudo`, polkit and your lock screen.

Found in, for example, the **Dell Inspiron 5575** (fingerprint reader in the
power button). Check if you have it:

```
lsusb | grep 27c6:5301
# Bus 003 Device 004: ID 27c6:5301 Shenzhen Goodix Technology Co.,Ltd. Fingerprint Reader
```

> **Status: works, early.** Tested on one laptop (Dell Inspiron 5575, Arch /
> Omarchy): enrolling and verifying through fprintd and libfprint's example
> programs, plus Omarchy's fingerprint setup for sudo, polkit and the lock
> screen (unlocking the Hyprland lock screen confirmed). Please open an issue with your laptop model if it works (or
> doesn't) for you.

## Install

Prebuilt packages are on the [Releases page](https://github.com/pirates-killer/libfprint-goodix-5301/releases).
Each one replaces the distribution's libfprint with upstream libfprint plus
this driver, so `fprintd` keeps working.

| Distribution | Package | Install |
|---|---|---|
| Ubuntu 24.04 (should also work on 24.04-based distros such as Linux Mint 22 and Pop!_OS 24.04) | `libfprint-2-2_…~ubuntu24.04_amd64.deb` | `sudo apt install ./libfprint-2-2_*~ubuntu24.04_amd64.deb fprintd libpam-fprintd` |
| Debian 12 | `libfprint-2-2_…~deb12_amd64.deb` | `sudo apt install ./libfprint-2-2_*~deb12_amd64.deb fprintd libpam-fprintd` |
| Fedora 45 | `libfprint-1.94.100-100.goodixmilanf1.fc45.x86_64.rpm` | `sudo dnf install ./libfprint-*.fc45.x86_64.rpm fprintd fprintd-pam` |
| Arch, Omarchy, Manjaro, EndeavourOS | `libfprint-goodixmilanf-…pkg.tar.zst` | `sudo pacman -U libfprint-goodixmilanf-*.pkg.tar.zst` (or build it, below) |

Then restart fprintd so it loads the new library: `sudo systemctl stop fprintd`.

Each package was built and install-tested next to the distribution's own
`fprintd` on a clean system: it replaces the stock libfprint, fprintd links
against it, and a normal `apt upgrade` / `dnf upgrade` keeps it. Only the
Arch build has been used with the actual reader so far.

**Keeping it installed:** the package version is higher than the
distribution's, so updates leave it alone. If your distribution ever ships a
newer libfprint, the update would replace it and the reader would stop
working until you install a newer build from here. To prevent that:
`sudo apt-mark hold libfprint-2-2` (Debian/Ubuntu) or
`sudo dnf versionlock add libfprint` (Fedora, needs `python3-dnf-plugin-versionlock`).

### Arch: build from source

```
git clone https://github.com/pirates-killer/libfprint-goodix-5301
cd libfprint-goodix-5301/arch
makepkg -si
```

The package replaces `libfprint` / `libfprint-git` (it provides both), so
`fprintd` and Omarchy's fingerprint setup keep working. It builds upstream
libfprint from source with the driver patch applied, and pulls in OpenCV.

### Debian, Ubuntu, Fedora: build the package yourself

On the release you want to install on (as root, or in a container of that
release):

```
git clone https://github.com/pirates-killer/libfprint-goodix-5301
sudo sh libfprint-goodix-5301/packaging/deb/build-deb.sh .      # Debian / Ubuntu
sudo sh libfprint-goodix-5301/packaging/rpm/build-rpm.sh .      # Fedora
```

### Any other distribution: build from source

You need libfprint's build dependencies plus OpenCV (4.4 or newer) and a C++
compiler. These dependency lists were checked on Debian 12, Ubuntu 24.04
and Fedora 45:

- Debian / Ubuntu: `sudo apt install git meson ninja-build gcc g++ pkg-config libglib2.0-dev libgusb-dev libgudev-1.0-dev libpixman-1-dev libssl-dev libopencv-dev udev`
- Fedora: `sudo dnf install git meson gcc gcc-c++ glib2-devel libgusb-devel libgudev-devel pixman-devel openssl-devel opencv-devel systemd-devel`

```
git clone https://gitlab.freedesktop.org/libfprint/libfprint.git
cd libfprint
git checkout 8b6e4e39bee58de2774222e3730269def470b157
git apply /path/to/libfprint-goodix-5301/patches/0001-goodixmilanf-Add-driver-for-Goodix-Milan-F-27c6-5301.patch
meson setup build --prefix=/usr -Ddoc=false -Dgtk-examples=false -Dintrospection=false
ninja -C build
sudo ninja -C build install
sudo install -m644 /path/to/libfprint-goodix-5301/udev/61-goodixmilanf.rules /usr/lib/udev/rules.d/
sudo udevadm control --reload && sudo systemctl stop fprintd
```

This writes over your distribution's libfprint outside the package manager,
so a system update can put the stock one back. Prefer a package where you
can. The patch should also apply to other recent libfprint versions (1.94.x).

## Set up fingerprint login

- **Omarchy:** run `omarchy-setup-security-fingerprint`.
- **Everywhere else:** `fprintd-enroll`, check with `fprintd-verify`, then
  enable `pam_fprintd` the usual way for your distribution (for example
  `sudo pam-auth-update` on Debian/Ubuntu, `authselect enable-feature with-fingerprint`
  on Fedora).

Enrolling takes 12 touches. Lift your finger fully between touches and move
it a little each time (higher, lower, left, right, slightly rotated). The
sensor only sees about 5 x 4 mm, so variety during enrollment is what makes
later touches match.

## Good to know

- **The first touch sometimes says "no match".** That happens when the
  touch lands on a part of the finger that wasn't enrolled. Touch again;
  `pam_fprintd` allows 3 tries before falling back to your password.
- **Security.** Matching uses SIGFM (see below), not libfprint's usual
  minutiae matcher, which can't work on a sensor this small. In testing,
  every wrong finger was rejected (highest wrong-finger score 18; a match
  needs 40), but that is a small test set (about 30 wrong-finger touches on one
  device), not a measured false-accept rate. Treat it as a convenience
  feature, and keep a strong password.
- **No Goodix files are included.** The driver talks to the reader's
  existing firmware. Nothing is flashed: the driver never sends the
  commands that write the reader's flash.
- **ModemManager.** The reader appears as a serial "modem" (`/dev/ttyACM*`).
  The included udev rule tells ModemManager to leave it alone. libfprint
  detaches the serial driver while it uses the reader.

## Troubleshooting

Run fprintd in the foreground with debug output, then use it from another
terminal:

```
sudo systemctl stop fprintd
sudo G_MESSAGES_DEBUG=all /usr/lib/fprintd -t     # Debian/Ubuntu: /usr/libexec/fprintd
# in another terminal:
fprintd-verify
```

Useful lines: `Chip ID: 0x2202`, `OTP calibration: ...`,
`finger on (var ..., shift ...)`, `verify score N (threshold 40)`.
`baseline contained a finger, retaking it` is normal when a finger was
resting on the sensor while the reader started.

`tools/` has a small Python tool that talks to the reader over its serial
port (no libfprint involved), useful for checking a new device:

```
sudo setfacl -m u:$USER:rw /dev/ttyACM0
python3 tools/info.py       # firmware, chip ID, OTP
python3 tools/capture.py    # one frame -> gx-captures/frame.pgm
```

It only sends read, reset, config and capture commands, and refuses flash,
erase and key commands.

## How it works

- `packaging/` — .deb/.rpm build scripts and the rootless distro test harness.
- `patches/` — the libfprint driver (`libfprint/drivers/goodixmilanf/`), as
  one patch against upstream libfprint.
- `docs/PROTOCOL.md` — the USB protocol: framing, init sequence, OTP
  calibration, image descrambling.
- The reader is a GF5288-family sensor behind an HT32 microcontroller. Its
  `HT_APP` firmware speaks the same Goodix message protocol as the
  27c6:5385/5395 readers, but without TLS. Images are XOR-scrambled with
  a fixed LFSR stream and protected by a CRC32.
- 108 x 88 pixels is too small for minutiae matching (0 to 2 minutiae per
  image), so the driver matches on the host with **SIGFM** (SIFT keypoints
  plus a geometric consistency check), with templates stored by fprintd like
  any other reader.

## Credits

- [libfprint](https://fprint.freedesktop.org/) and its authors.
- [goodix-fp-dump](https://github.com/goodix-fp-linux-dev/goodix-fp-dump) —
  the Goodix message protocol and the 53x5 (GF5288 HTSEC) work this builds on.
- SIGFM by Matthieu Charette, Natasha England-Elbro and Timur Mangliev
  ([goodix-fp-linux-dev](https://github.com/goodix-fp-linux-dev),
  [libfprint MR !418](https://gitlab.freedesktop.org/libfprint/libfprint/-/merge_requests/418)).

Not affiliated with Goodix or Dell. The protocol was reverse engineered for
interoperability.

## License

LGPL-2.1-or-later, the same as libfprint. See `LICENSE`.
