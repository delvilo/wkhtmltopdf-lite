#!/usr/bin/env bash
# Run with sudo on an Ubuntu 24.04 x86_64 build host. LGPL-3.0-or-later.
set -euo pipefail
source /etc/os-release
[[ "$ID:$VERSION_ID:$(uname -m)" == ubuntu:24.04:x86_64 && "$EUID" == 0 ]] || {
    echo 'Run with sudo on Ubuntu 24.04 x86_64.' >&2; exit 1;
}
# Source repositories are necessary for the exact corresponding source bundle.
cat > /etc/apt/sources.list.d/wkhtmltox-sources.sources <<'APT'
Types: deb-src
URIs: http://archive.ubuntu.com/ubuntu
Suites: noble noble-updates
Components: main universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb-src
URIs: http://security.ubuntu.com/ubuntu
Suites: noble-security
Components: main universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
APT
apt-get update
apt-get install -y --no-install-recommends build-essential cmake ninja-build \
    pkg-config python3 perl ruby bison flex gperf dpkg-dev xz-utils git \
    libssl-dev zlib1g-dev libpng-dev libjpeg-dev libicu-dev libxml2-dev \
    libsqlite3-dev libwebp-dev libhyphen-dev libfontconfig1-dev libfreetype-dev \
    libpcre2-dev liblzma-dev fonts-dejavu-core fonts-noto-cjk ca-certificates \
    openssl poppler-utils
