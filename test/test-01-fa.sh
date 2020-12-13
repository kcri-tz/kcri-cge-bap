#!/bin/sh

LC_ALL="C"

BASE_NAME="$(basename "$0" .sh)"
BASE_DIR="$(realpath "$(dirname "$0")")"

export BAP_DB_DIR="$BASE_DIR/databases"

. "$BASE_DIR/functions.sh"

make_workdir

cp "$BASE_DIR/data/test.fa.gz" "$BAP_WORK_DIR/"

run_bap -v "test.fa.gz"

rm -f "$BAP_WORK_DIR/test.fa.gz"

check_output

