#!/bin/sh

LC_ALL="C"

BASE_NAME="$(basename "$0" .sh)"
BASE_DIR="$(realpath "$(dirname "$0")")"

. "$BASE_DIR/functions.sh"

make_workdir

cp "$BASE_DIR/data/test_1.fq.gz" "$BASE_DIR/data/test_2.fq.gz" "$BAP_WORK_DIR/"

run_bap -v --sq-p Illumina --sq-r paired "test_1.fq.gz" "test_2.fq.gz"

rm -f "$BAP_WORK_DIR/test_1.fq.gz" "$BAP_WORK_DIR/test_2.fq.gz"

check_output

