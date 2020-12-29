#!/bin/sh

LC_ALL="C"

BASE_NAME="$(basename "$0" .sh)"
BASE_DIR="$(realpath "$(dirname "$0")")"

. "$BASE_DIR/functions.sh"

make_output_dir
run_bap -v -o "$OUTPUT_DIR" -x PointFinder -t metrics,resistance -s 'Escherichia coli' \
    "$BASE_DIR/../ext/resfinder/tests/data/test_isolate_01_1.fq" "$BASE_DIR/../ext/resfinder/tests/data/test_isolate_01_2.fq"
check_output

