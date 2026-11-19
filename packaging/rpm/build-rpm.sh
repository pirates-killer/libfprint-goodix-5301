#!/bin/sh
# Build the replacement libfprint RPM on the target Fedora release (as root,
# e.g. in a container):  sh build-rpm.sh [OUTDIR]
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
OUT=${1:-$PWD}
COMMIT=$(sed -n 's/^%global commit //p' "$HERE/libfprint-goodixmilanf.spec")
SHORT=$(echo "$COMMIT" | cut -c1-8)

dnf -y -q install rpm-build rpmdevtools git-core meson gcc gcc-c++ glib2-devel libgusb-devel \
  libgudev-devel pixman-devel openssl-devel opencv-devel systemd-devel systemd-rpm-macros >/dev/null

TOP=$(mktemp -d)
mkdir -p "$TOP/SOURCES" "$TOP/SPECS"
git clone -q https://gitlab.freedesktop.org/libfprint/libfprint.git "$TOP/src"
git -C "$TOP/src" archive --format=tar.gz --prefix="libfprint-$SHORT/" "$COMMIT" \
  > "$TOP/SOURCES/libfprint-$SHORT.tar.gz"
cp "$REPO/patches/0001-goodixmilanf-Add-driver-for-Goodix-Milan-F-27c6-5301.patch" \
   "$REPO/udev/61-goodixmilanf.rules" "$TOP/SOURCES/"
cp "$HERE/libfprint-goodixmilanf.spec" "$TOP/SPECS/"
rpmbuild --define "_topdir $TOP" -bb "$TOP/SPECS/libfprint-goodixmilanf.spec" >"$TOP/build.log" 2>&1 \
  || { tail -40 "$TOP/build.log"; exit 1; }
find "$TOP/RPMS" -name 'libfprint-1*.rpm' ! -name '*debug*' -exec cp {} "$OUT/" \; -print | sed "s|.*/|$OUT/|"
