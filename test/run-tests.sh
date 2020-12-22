#!/bin/sh
#
# Runs test-* and if $1 is set to anything the slow-* too.
#

set -e

cd $(dirname "$0")

for T in test-*.sh; do ./$T; done
[ -z "$1" ] || for T in slow-*.sh; do ./$T; done

