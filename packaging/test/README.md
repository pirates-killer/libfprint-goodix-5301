# Distro build/install tests (no Docker or root needed)

Rootless test harness used to check the build and the packages on other
distributions. It downloads official Docker Hub base images with plain
HTTPS and runs them as chroots inside an unprivileged user namespace
(`unshare --map-auto`, needs `newuidmap` and a `/etc/subuid` entry).

```
cd packaging/test
python3 fetch_image.py library/ubuntu 24.04 img-ubuntu2404
mkdir rootfs-ubuntu2404
unshare --map-auto --map-root-user tar -xzf img-ubuntu2404/layer-0.tar.gz -C rootfs-ubuntu2404 --numeric-owner
unshare --map-auto --map-root-user cp build-test.sh rootfs-ubuntu2404/root/

# build + meson test (README dependency list), with the repo mounted at /share
GX_SHARE=$(cd ../.. && pwd) ./enter.sh ubuntu2404 sh /root/build-test.sh

# build a package into dist/
GX_SHARE=$(cd ../.. && pwd) ./enter.sh ubuntu2404 sh /share/packaging/deb/build-deb.sh /share/dist

# install-test it next to fprintd on a fresh rootfs (install-test.sh)
```

`build-rpm.sh` does the same for Fedora.
