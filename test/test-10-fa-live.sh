#!/bin/sh

LC_ALL="C"

BASE_NAME="$(basename "$0" .sh)"
BASE_DIR="$(realpath "$(dirname "$0")")"

. "$BASE_DIR/functions.sh"

make_output_dir
run_bap -v -o "$OUTPUT_DIR" "$BASE_DIR/data/test.fa"
check_output

