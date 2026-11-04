#!/bin/sh
set -eu

version=${1-}
case "$version" in
    18.*) minor=${version#18.} ;;
    *) echo "expected PostgreSQL >=18.6,<19, got: $version" >&2; exit 2 ;;
esac
case "$minor" in
    ''|*[!0-9]*) echo "invalid PostgreSQL minor: $version" >&2; exit 2 ;;
esac
if [ "$minor" -lt 6 ] || [ "$#" -ne 1 ]; then
    echo "expected one PostgreSQL >=18.6,<19 version" >&2
    exit 2
fi

if command -v apk >/dev/null 2>&1; then
    apk add --no-cache ca-certificates curl build-base perl linux-headers bzip2 bison flex
fi

build_root=$(mktemp -d)
trap 'rm -rf "$build_root"' 0
trap 'exit 1' HUP INT TERM
cd "$build_root"

archive="postgresql-$version.tar.bz2"
source_url="https://ftp.postgresql.org/pub/source/v$version/$archive"
curl --fail --show-error --location --retry 3 "$source_url" --output "$archive"
curl --fail --show-error --location --retry 3 "$source_url.sha256" --output "$archive.sha256"
sha256sum -c "$archive.sha256"
tar -xjf "$archive"
cd "postgresql-$version"
./configure --prefix=/opt/wheel-libpq --without-icu --without-readline --without-zlib
make -j2
make install
/opt/wheel-libpq/bin/pg_config --version
