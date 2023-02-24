#!/bin/sh

LC_ALL="C"

BASE_NAME="$(basename "$0" .sh)"
BASE_DIR="$(realpath "$(dirname "$0")")"

export BAP_DB_DIR="$BASE_DIR/databases"

. "$BASE_DIR/functions.sh"

make_output_dir
run_bap -v -o "$OUTPUT_DIR" "$BASE_DIR/data/nano.fq.gz"
check_output || {
  echo "CHECK the above, probably good"
  true
}

