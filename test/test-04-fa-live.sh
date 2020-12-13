#!/bin/sh

LC_ALL="C"

BASE_NAME="$(basename "$0" .sh)"
BASE_DIR="$(realpath "$(dirname "$0")")"

. "$BASE_DIR/functions.sh"

make_workdir

cp "$BASE_DIR/data/test.fa" "$BAP_WORK_DIR/"

run_bap -v "test.fa"

rm -f "$BAP_WORK_DIR/test.fa"

check_output

