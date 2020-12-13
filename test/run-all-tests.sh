#!/bin/sh

set -e

cd $(dirname "$0")

for T in test-*.sh; do ./$T; done

