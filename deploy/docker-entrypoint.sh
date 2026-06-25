#!/bin/sh
set -e

# /data and /config may be bind mounts created as root; make them writable for the
# unprivileged app user, then drop privileges so the app never runs as root.
if [ "$(id -u)" = "0" ]; then
    chown -R app:app /data /config 2>/dev/null || true
    exec gosu app "$@"
fi

exec "$@"
