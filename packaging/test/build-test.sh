#!/bin/sh
# Runs INSIDE a distro rootfs. /share = the release repo.
set -e
. /etc/os-release
echo "=== $PRETTY_NAME"
case "$ID" in
  debian|ubuntu)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    # exactly the README list, plus ca-certificates for git over https
    apt-get install -y -qq git meson ninja-build gcc g++ pkg-config libglib2.0-dev libgusb-dev \
      libgudev-1.0-dev libpixman-1-dev libssl-dev libopencv-dev udev ca-certificates >/dev/null
    ;;
  fedora)
    dnf -y -q install git meson gcc gcc-c++ glib2-devel libgusb-devel libgudev-devel pixman-devel \
      openssl-devel opencv-devel systemd-devel >/dev/null
    ;;
esac
echo "meson $(meson --version), opencv $(pkg-config --modversion opencv5 2>/dev/null || pkg-config --modversion opencv4)"
cd /root
rm -rf libfprint
git clone -q https://gitlab.freedesktop.org/libfprint/libfprint.git
cd libfprint
git -c advice.detachedHead=false checkout -q 8b6e4e39bee58de2774222e3730269def470b157
git apply /share/patches/0001-goodixmilanf-Add-driver-for-Goodix-Milan-F-27c6-5301.patch
meson setup build --prefix=/usr -Ddoc=false -Dgtk-examples=false -Dintrospection=false >/root/meson-setup.log 2>&1 || { tail -30 /root/meson-setup.log; exit 1; }
ninja -C build >/root/ninja.log 2>&1 || { grep -E "error|FAILED" /root/ninja.log | head -30; exit 1; }
grep -cE "warning:" /root/ninja.log | sed 's/^/compiler warnings: /'
grep -E "goodixmilanf.*warning:" /root/ninja.log | head -10 || true
meson test -C build --print-errorlogs 2>&1 | grep -E "^(Ok|Fail|Skipped|Expected Fail|Timeout):|FAIL" || true
strings build/libfprint/libfprint-2.so.2.0.0 | grep -c "Goodix Milan F" | sed 's/^/driver strings in lib: /'
echo "=== BUILD OK on $PRETTY_NAME"
