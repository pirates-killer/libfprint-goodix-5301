#!/bin/sh
# usage: enter.sh NAME CMD...   run CMD as (namespaced) root inside rootfs-NAME
d=$(cd "$(dirname "$0")" && pwd)/rootfs-$1; shift
exec unshare --map-auto --map-root-user --mount --pid --fork sh -c '
  r=$1; shift
  mount -t proc proc "$r/proc"
  mount --rbind /dev "$r/dev"
  mount --rbind /sys "$r/sys" 2>/dev/null
  mount -t tmpfs tmpfs "$r/tmp"
  cp /etc/resolv.conf "$r/etc/resolv.conf"
  [ -n "$GX_SHARE" ] && mkdir -p "$r/share" && mount --bind "$GX_SHARE" "$r/share"
  exec chroot "$r" /usr/bin/env -i HOME=/root TERM=xterm PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8 "$@"
' sh "$d" "$@"
