#!/bin/sh

LC_ALL="C"

BASE_NAME="$(basename "$0" .sh)"
BASE_DIR="$(realpath "$(dirname "$0")")"

export BAP_DB_DIR="$BASE_DIR/databases"

. "$BASE_DIR/functions.sh"

make_output_dir
run_bap -v -t metrics -o "$OUTPUT_DIR" "$BASE_DIR/data/test.fa.gz"
check_output

