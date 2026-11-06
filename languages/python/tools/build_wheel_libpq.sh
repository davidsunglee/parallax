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
prefix=/opt/wheel-libpq

install_build_dependencies() {
    for attempt in 1 2 3; do
        if "$1" install -y flex bison perl; then
            return 0
        else
            status=$?
        fi
        if [ "$attempt" -eq 3 ]; then
            return "$status"
        fi
        echo "$1 install failed (attempt $attempt/3); retrying in 5 seconds" >&2
        sleep 5
        # Discard malformed repository metadata before the next install fetches it.
        "$1" clean all
    done
}

if command -v dnf >/dev/null 2>&1; then
    install_build_dependencies dnf
elif command -v yum >/dev/null 2>&1; then
    install_build_dependencies yum
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
sha256sum -c "$archive.sha256"
tar -xjf "$archive"
cd "postgresql-$version"
./configure --prefix="$prefix" --without-icu --without-readline --without-zlib
make -j2
make install
make -C contrib/btree_gist -j2
make -C contrib/btree_gist install
"$prefix/bin/pg_config" --version
