#!/bin/sh

LC_ALL="C"

BASE_NAME="$(basename "$0" .sh)"
BASE_DIR="$(realpath "$(dirname "$0")")"

export BAP_DB_DIR="$BASE_DIR/databases"

. "$BASE_DIR/functions.sh"

make_output_dir
run_bap -v -t graph -o "$OUTPUT_DIR" "$BASE_DIR/data/nano.fq.gz"
check_output

[ -f "$OUTPUT_DIR/Flye/assembly_graph.gfa" ] || { echo "[FAIL] no graph file"; exit 1; }
