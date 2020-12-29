#!/bin/sh

LC_ALL="C"

BASE_NAME="$(basename "$0" .sh)"
BASE_DIR="$(realpath "$(dirname "$0")")"

. "$BASE_DIR/functions.sh"

make_output_dir
run_bap -v -o "$OUTPUT_DIR" -x ResFinder -t metrics,resistance -s 'Escherichia coli' \
    "$BASE_DIR/../ext/resfinder/tests/data/test_isolate_05.fa"	
check_output

