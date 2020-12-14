#!/bin/sh
#
# make-kcst-db.sh - invokes the 'real' make-kcst-db.sh which lives in the container
#

# Need to set BAP_DB_DIR (to an arbitrary directory) if it is not set.
export BAP_DB_DIR="${BAP_DB_DIR:-/tmp}"

# Invoke the kma_index in the container with our arguments as its arguments
exec "$(realpath -e "$(dirname "$0")/../bin/bap-container-run")" make-kcst-db.sh "$@"

# vim: sts=4:sw=4:ai:si:et
