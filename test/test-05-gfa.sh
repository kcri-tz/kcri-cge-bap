#!/bin/sh

LC_ALL="C"

BASE_NAME="$(basename "$0" .sh)"
BASE_DIR="$(realpath "$(dirname "$0")")"

export BAP_DB_DIR="$BASE_DIR/databases"

. "$BASE_DIR/functions.sh"

make_output_dir
run_bap -v -t graph -o "$OUTPUT_DIR" "$BASE_DIR/data/test_1.fq.gz" "$BASE_DIR/data/test_2.fq.gz"
check_output

[ -f "$OUTPUT_DIR/GFAConnector/contigs.gfa" ] || { echo "[FAIL] no graph file"; exit 1; }
