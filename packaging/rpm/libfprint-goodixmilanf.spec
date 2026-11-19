# libfprint + goodixmilanf driver for the Goodix 27c6:5301 fingerprint reader.
# Replaces Fedora's libfprint (same name, higher version), so fprintd keeps working.
%global commit 8b6e4e39bee58de2774222e3730269def470b157
%global shortcommit %(c=%{commit}; echo ${c:0:8})

Name:           libfprint
Version:        1.94.100
Release:        100.goodixmilanf1%{?dist}
Summary:        Fingerprint library with the Goodix 27c6:5301 (Milan F) driver
License:        LGPL-2.1-or-later
URL:            https://github.com/pirates-killer/libfprint-goodix-5301
Source0:        libfprint-%{shortcommit}.tar.gz
Source1:        61-goodixmilanf.rules
Patch0:         0001-goodixmilanf-Add-driver-for-Goodix-Milan-F-27c6-5301.patch

BuildRequires:  meson gcc gcc-c++ git-core
BuildRequires:  glib2-devel libgusb-devel libgudev-devel pixman-devel
BuildRequires:  openssl-devel opencv-devel systemd-devel
BuildRequires:  systemd-rpm-macros

%description
Upstream libfprint (commit %{shortcommit}) plus the goodixmilanf driver for
the Goodix 27c6:5301 ("Milan F") fingerprint reader found in e.g. the Dell
Inspiron 5575. Built from https://github.com/pirates-killer/libfprint-goodix-5301

%prep
%autosetup -n libfprint-%{shortcommit} -p1

%build
%meson -Ddoc=false -Dgtk-examples=false -Dintrospection=false \
       -Dinstalled-tests=false -Dudev_hwdb=enabled
%meson_build

%install
%meson_install
install -Dm644 %{SOURCE1} %{buildroot}%{_udevrulesdir}/61-goodixmilanf.rules
# runtime package only
rm -rf %{buildroot}%{_includedir} %{buildroot}%{_libdir}/pkgconfig %{buildroot}%{_libdir}/libfprint-2.so

%files
%license COPYING
%{_libdir}/libfprint-2.so.2*
%{_udevrulesdir}/70-libfprint-2.rules
%{_udevrulesdir}/61-goodixmilanf.rules
%{_udevhwdbdir}/60-autosuspend-libfprint-2.hwdb
%{_datadir}/metainfo/org.freedesktop.libfprint.metainfo.xml

%changelog
* Fri Nov 20 2026 pirates-killer - 1.94.100-100.goodixmilanf1
- Upstream libfprint 8b6e4e39 with the goodixmilanf driver
