#!/bin/sh
# Build a .deb that replaces the distribution's libfprint-2-2 with
# libfprint + the goodixmilanf driver. Run on the target Debian/Ubuntu
# release (as root, e.g. in a container):  sh build-deb.sh [OUTDIR]
set -eu
COMMIT=8b6e4e39bee58de2774222e3730269def470b157
UPVER=1.94.100
PKGREV=1
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
OUT=${1:-$PWD}
. /etc/os-release
case "$ID" in
  debian) SUFFIX="deb${VERSION_ID}" ;;
  ubuntu) SUFFIX="ubuntu${VERSION_ID}" ;;
  *) SUFFIX="$ID${VERSION_ID:-}" ;;
esac
VERSION="1:${UPVER}+goodixmilanf${PKGREV}~${SUFFIX}"
ARCH=$(dpkg --print-architecture)

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git meson ninja-build gcc g++ pkg-config libglib2.0-dev libgusb-dev \
  libgudev-1.0-dev libpixman-1-dev libssl-dev libopencv-dev udev ca-certificates dpkg-dev >/dev/null

W=$(mktemp -d)
git clone -q https://gitlab.freedesktop.org/libfprint/libfprint.git "$W/libfprint"
cd "$W/libfprint"
git -c advice.detachedHead=false checkout -q "$COMMIT"
git apply "$REPO/patches/0001-goodixmilanf-Add-driver-for-Goodix-Milan-F-27c6-5301.patch"
meson setup build --prefix=/usr --buildtype=release -Ddoc=false -Dgtk-examples=false \
  -Dintrospection=false -Dinstalled-tests=false -Dudev_hwdb=enabled >/dev/null
ninja -C build >/dev/null
DESTDIR="$W/root" meson install -C build >/dev/null

R="$W/root"
# runtime package only: drop development files (they belong to libfprint-2-dev)
rm -rf "$R/usr/include" "$R/usr/share/gir-1.0"
find "$R" -name '*.pc' -delete
find "$R" -name 'libfprint-2.so' -type l -delete
find "$R" -type d -name pkgconfig -empty -delete
install -Dm644 "$REPO/udev/61-goodixmilanf.rules" "$R/usr/lib/udev/rules.d/61-goodixmilanf.rules"
LIB=$(find "$R" -name 'libfprint-2.so.2.*' -type f)
strip --strip-unneeded "$LIB"

# dependencies from the linked libraries
mkdir -p "$W/shl/debian"
printf 'Source: libfprint\n\nPackage: libfprint-2-2\nArchitecture: any\n' > "$W/shl/debian/control"
DEPS=$(cd "$W/shl" && dpkg-shlibdeps -O "$LIB" 2>/dev/null | sed -n 's/^shlibs:Depends=//p')

mkdir -p "$R/DEBIAN"
cat > "$R/DEBIAN/control" <<CTRL
Package: libfprint-2-2
Version: $VERSION
Architecture: $ARCH
Maintainer: libfprint-goodix-5301 <https://github.com/pirates-killer/libfprint-goodix-5301>
Section: libs
Priority: optional
Depends: $DEPS
Homepage: https://github.com/pirates-killer/libfprint-goodix-5301
Description: fingerprint library, with the Goodix 27c6:5301 (Milan F) driver
 Upstream libfprint (commit ${COMMIT%${COMMIT#????????}}) plus the goodixmilanf
 driver for the Goodix 27c6:5301 fingerprint reader. Replaces the
 distribution's libfprint-2-2; fprintd keeps working.
CTRL
echo "activate-noawait ldconfig" > "$R/DEBIAN/triggers"
cat > "$R/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
  command -v systemd-hwdb >/dev/null && systemd-hwdb update || true
  command -v udevadm >/dev/null && udevadm control --reload 2>/dev/null || true
fi
POST
chmod 755 "$R/DEBIAN/postinst"
NAME="libfprint-2-2_${UPVER}+goodixmilanf${PKGREV}~${SUFFIX}_${ARCH}.deb"
dpkg-deb --root-owner-group -Zxz --build "$R" "$OUT/$NAME" >/dev/null
echo "$OUT/$NAME"
