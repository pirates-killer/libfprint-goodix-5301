#!/bin/sh
# INSIDE a clean rootfs: install fprintd (stock libfprint), then our package over it.
set -e
. /etc/os-release
echo "=== $PRETTY_NAME"
case "$ID" in
  debian|ubuntu)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq fprintd libpam-fprintd >/dev/null 2>&1
    echo "stock: $(dpkg-query -W -f='${Package} ${Version}' libfprint-2-2)"
    f=$(ls /share/dist/*~$( [ "$ID" = debian ] && echo deb$VERSION_ID || echo ubuntu$VERSION_ID )_*.deb)
    apt-get install -y -qq "$f" 2>&1 | grep -viE "^(debconf|Selecting|Preparing|Unpacking|Setting up|Processing|\(Reading)" || true
    echo "now:   $(dpkg-query -W -f='${Package} ${Version} ${Status}' libfprint-2-2)"
    echo "fprintd: $(dpkg-query -W -f='${Version} ${Status}' fprintd)"
    bin=$(ls /usr/libexec/fprintd /usr/lib/fprintd 2>/dev/null | head -1)
    ldd "$bin" | grep -E "fprint|not found"
    apt-get -s -qq upgrade | grep -i libfprint || echo "apt upgrade: keeps our libfprint"
    apt-get -s -qq install libfprint-2-2 2>&1 | grep -i "newest\|libfprint" | head -2
    ;;
  fedora)
    dnf -y -q install fprintd fprintd-pam >/dev/null 2>&1
    echo "stock: $(rpm -q libfprint)"
    dnf -y -q install /share/dist/libfprint-*.fc45.x86_64.rpm >/dev/null 2>&1
    echo "now:   $(rpm -q libfprint)"
    echo "fprintd: $(rpm -q fprintd)"
    ldd /usr/libexec/fprintd | grep -E "fprint|not found"
    dnf -q check && echo "dnf check: OK"
    dnf -q --assumeno upgrade libfprint 2>&1 | grep -i "libfprint" || echo "dnf upgrade: keeps our libfprint"
    ;;
esac
lib=$(ls /usr/lib*/libfprint-2.so.2.0.0 /usr/lib/*/libfprint-2.so.2.0.0 2>/dev/null | head -1)
grep -c "Goodix Milan F" "$lib" | sed 's/^/driver in installed lib: /'
ls /usr/lib/udev/rules.d/ | grep -E "goodix|libfprint"
echo "=== INSTALL OK"
