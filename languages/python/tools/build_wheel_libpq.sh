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
if [ "$minor" -lt 6 ] || [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "expected a PostgreSQL >=18.6,<19 version and optional installation prefix" >&2
    exit 2
fi
prefix=${2-/opt/wheel-libpq}
case "$prefix" in
    /*) ;;
    *) echo "expected an absolute installation prefix" >&2; exit 2 ;;
esac

if command -v apk >/dev/null 2>&1; then
    apk add --no-cache ca-certificates curl build-base perl linux-headers bzip2 bison flex
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y flex bison perl
elif command -v yum >/dev/null 2>&1; then
    yum install -y flex bison perl
fi

build_root=$(mktemp -d)
trap 'rm -rf "$build_root"' 0
trap 'exit 1' HUP INT TERM
cd "$build_root"

archive="postgresql-$version.tar.bz2"
source_url="https://ftp.postgresql.org/pub/source/v$version/$archive"
curl --fail --show-error --location --retry 3 "$source_url" --output "$archive"
curl --fail --show-error --location --retry 3 "$source_url.sha256" --output "$archive.sha256"
cat "$archive.sha256"
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c "$archive.sha256"
else
    shasum -a 256 -c "$archive.sha256"
fi
tar -xjf "$archive"
cd "postgresql-$version"
./configure --prefix="$prefix" --without-icu --without-readline --without-zlib
make -j2
make install
make -C contrib/btree_gist -j2
make -C contrib/btree_gist install
"$prefix/bin/pg_config" --version
